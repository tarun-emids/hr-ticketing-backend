"""Employee ticket drafts: CRUD, submit, attachments. Rules live in
DraftService (ownership scoping, submit validation, attachment swap)."""
from fastapi import APIRouter, Depends, UploadFile

from app.config import SIGNED_URL_TTL
from app.deps import get_draft_service
from app.models import DraftCreate, DraftSubmit, DraftUpdate
from app.services.draft_service import DraftService

router = APIRouter(prefix="/drafts", tags=["drafts"])

STATUS_NO_BODY = 204


@router.get("")
def list_drafts(employeeId: str, svc: DraftService = Depends(get_draft_service)):
    """GET /drafts?employeeId=... — drafts belonging to one employee."""
    return svc.list_drafts(employeeId)


@router.post("", status_code=201)
def create_draft(payload: DraftCreate, svc: DraftService = Depends(get_draft_service)):
    """POST /drafts — save an incomplete ticket form."""
    return svc.create_draft(
        employee_id=payload.employee_id,
        category=payload.category,
        subject=payload.subject,
        description=payload.description,
        priority=payload.priority,
    )


@router.get("/{draft_id}")
def get_draft(draft_id: str, employeeId: str, svc: DraftService = Depends(get_draft_service)):
    return svc.get_draft(draft_id, employeeId)


@router.patch("/{draft_id}")
def update_draft(
    draft_id: str,
    employeeId: str,
    payload: DraftUpdate,
    svc: DraftService = Depends(get_draft_service),
):
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    return svc.update_draft(draft_id, employeeId, patch)


@router.delete("/{draft_id}", status_code=STATUS_NO_BODY)
def delete_draft(draft_id: str, employeeId: str, svc: DraftService = Depends(get_draft_service)):
    svc.delete_draft(draft_id, employeeId)


@router.post("/{draft_id}/submit")
def submit_draft(draft_id: str, payload: DraftSubmit, svc: DraftService = Depends(get_draft_service)):
    """Validate and convert the saved draft into a normal ticket."""
    return svc.submit_draft(draft_id, employee_id=payload.employee_id)


@router.post("/{draft_id}/attachment")
def upload_draft_attachment(
    draft_id: str,
    employeeId: str,
    file: UploadFile,
    svc: DraftService = Depends(get_draft_service),
):
    data = file.file.read()
    return svc.upload_attachment(
        draft_id, employeeId, filename=file.filename,
        content_type=file.content_type, data=data,
    )


@router.delete("/{draft_id}/attachment", status_code=STATUS_NO_BODY)
def delete_draft_attachment(
    draft_id: str, employeeId: str, svc: DraftService = Depends(get_draft_service),
):
    svc.delete_attachment(draft_id, employeeId)


@router.get("/{draft_id}/attachment")
def draft_attachment_url(
    draft_id: str,
    employeeId: str,
    ttl: int = SIGNED_URL_TTL,
    svc: DraftService = Depends(get_draft_service),
):
    return svc.attachment_url(draft_id, employeeId, ttl)
