"""Ticket attachment endpoints (multipart upload + signed URL).

The file bytes are read here (that is the HTTP-facing concern) — everything
else — size cap, path, storage I/O, the signed URL — belongs to the layers
below.

Observability: ``attachment.upload`` / ``attachment.url`` events. Request
descriptors (ticket ref, size, content type) ride BOTH boundary events;
completed adds expiry metadata. The signed URL (one-time token inside) and
the attachment NAME are never logged.
"""

from fastapi import APIRouter, Depends, UploadFile

from app.config import SIGNED_URL_TTL
from app.deps import get_ticket_service
from app.observability import flow_operation
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
    ttl: int = SIGNED_URL_TTL,
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /tickets/{id}/attachment — short-lived signed URL for the file.
    The URL (one-time token inside) is never logged; TTL and expiry only."""
    with flow_operation(
        "attachment.url",
        operation="tickets.attachment_url",
        method="GET",
        path=f"/api/tickets/{tid}/attachment",
        ticket_ref=tid,
        ttl=ttl,
    ) as op:
        result = svc.attachment_url(tid, ttl)
        op["expires_in"] = result.get("expiresInSeconds")
        op["size"] = result.get("size")
        return result
