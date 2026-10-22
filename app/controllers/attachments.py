"""Ticket attachment endpoints (multipart upload + signed URL).

The file bytes are read here (that is the HTTP-facing concern) — everything
else — size cap, path, storage I/O, the signed URL — belongs to the layers
below.
"""

from fastapi import APIRouter, Depends, UploadFile

from app.config import SIGNED_URL_TTL
from app.deps import get_ticket_service
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
    """GET /tickets/{id}/attachment — short-lived signed URL for the file."""
    return svc.attachment_url(tid, ttl)
