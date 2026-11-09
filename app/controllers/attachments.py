"""Ticket attachment endpoints (multipart upload + signed download URL).

The file bytes are read here (that is the HTTP-facing concern) — everything
else — size cap, path, storage I/O, the signed URL — belongs to the layers
below.

Observability: ``attachment.upload`` / ``attachment.url`` events. Request
descriptors (ticket ref, size, content type) ride BOTH boundary events;
completed adds expiry metadata. The signed URL (one-time token inside) and
the attachment NAME are never logged.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile

from app.config import SIGNED_URL_TTL
from app.deps import get_current_account, get_storage_repo, get_ticket_service
from app.observability import flow_operation
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.services.ticket_service import TicketService

router = APIRouter(tags=["attachments"])

_HR_ROLES = ("agent", "admin")


def _ensure_attachment_access(ticket: dict, account: dict) -> None:
    """Employees may handle attachments of their OWN tickets only; agents and
    admins handle any (the worktable runs on them)."""
    if account.get("role") not in _HR_ROLES and str(ticket.get("employeeId")) != str(account["id"]):
        raise HTTPException(status_code=403, detail="Not your ticket.")


@router.post("/tickets/{tid}/attachment")
def upload_attachment(
    tid: str,
    file: UploadFile,
    account: dict = Depends(get_current_account),
    svc: TicketService = Depends(get_ticket_service),
):
    """POST /tickets/{id}/attachment — multipart upload, <=5 MB."""
    data = file.file.read()
    _ensure_attachment_access(svc.get(tid), account)
    with flow_operation(
        "attachment.upload",
        operation="tickets.attachment_upload",
        method="POST",
        path=f"/api/tickets/{tid}/attachment",
        ticket_ref=tid,
        actor_id=str(account["id"]),
        size_bytes=len(data),
        content_type=file.content_type,
    ):
        return svc.upload_attachment(
            tid,
            filename=file.filename,
            content_type=file.content_type,
            data=data,
        )


@router.get("/tickets/{tid}/attachment")
def attachment_url(
    tid: str,
    request: Request,
    ttl: int = SIGNED_URL_TTL,
    account: dict = Depends(get_current_account),
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /tickets/{id}/attachment — short-lived signed URL for the file."""
    _ensure_attachment_access(svc.get(tid), account)
    with flow_operation(
        "attachment.url",
        operation="tickets.attachment_url",
        method="GET",
        path=f"/api/tickets/{tid}/attachment",
        ticket_ref=tid,
        actor_id=str(account["id"]),
    ) as event:
        result = svc.attachment_url(tid, ttl)
        result["url"] = f"{str(request.base_url).rstrip('/')}{result['url']}"
        event["expires_in_seconds"] = result["expiresInSeconds"]
        return result


@router.get("/attachments/file/{token}", name="download_attachment")
def download_attachment(
    token: str,
    storage: AttachmentStorageRepository = Depends(get_storage_repo),
):
    """Serve a file only when the caller presents a valid, unexpired signature."""
    data, content_type = storage.read_signed(token)
    return Response(content=data, media_type=content_type)
