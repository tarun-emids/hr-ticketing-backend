"""Ticket attachment endpoints (multipart upload + signed download URL).

The file bytes are read here (that is the HTTP-facing concern) — everything
else — size cap, path, storage I/O, the signed URL — belongs to the layers
below.

Observability: ``attachment.upload`` / ``attachment.url`` events. Request
descriptors (ticket ref, size, content type) ride BOTH boundary events;
completed adds expiry metadata. The signed URL (one-time token inside) and
the attachment NAME are never logged.
"""

from fastapi import APIRouter, Depends, Request, Response, UploadFile

from app.config import SIGNED_URL_TTL
from app.deps import get_storage_repo, get_ticket_service
from app.observability import flow_operation
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.services.ticket_service import TicketService

router = APIRouter(tags=["attachments"])


@router.post("/tickets/{tid}/attachment")
def upload_attachment(
    tid: str,
    file: UploadFile,
    svc: TicketService = Depends(get_ticket_service),
):
    """POST /tickets/{id}/attachment — multipart upload, <=5 MB."""
    data = file.file.read()
    with flow_operation(
        "attachment.upload",
        operation="tickets.attachment_upload",
        method="POST",
        path=f"/api/tickets/{tid}/attachment",
        ticket_ref=tid,
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
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /tickets/{id}/attachment — short-lived signed URL for the file."""
    with flow_operation(
        "attachment.url",
        operation="tickets.attachment_url",
        method="GET",
        path=f"/api/tickets/{tid}/attachment",
        ticket_ref=tid,
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
