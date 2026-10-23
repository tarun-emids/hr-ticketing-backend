"""Employee ticket drafts: CRUD, submit, attachments. Rules live in
DraftService (ownership scoping, submit validation, attachment swap).
Observability: every endpoint emits the ``drafts.*`` started/completed/failed
trio (hrdesk.flow) — ``drafts.attachment.*`` for the attachment routes. Safe
metadata only: employee/draft uuids, which optional patch fields were set
(field NAMES from the validated DTO, never values), attachment sizes and
content types. Draft subjects/descriptions(/file names) are never logged.
"""

from fastapi import APIRouter, Depends, Request, UploadFile

from app.config import SIGNED_URL_TTL
from app.deps import get_draft_service
from app.models import DraftCreate, DraftSubmit, DraftUpdate
from app.observability import flow_operation
from app.services.draft_service import DraftService

router = APIRouter(prefix="/drafts", tags=["drafts"])

STATUS_NO_BODY = 204


@router.get("")
def list_drafts(employeeId: str, svc: DraftService = Depends(get_draft_service)):
    """GET /drafts?employeeId=... — drafts belonging to one employee."""
    with flow_operation(
        "drafts.list",
        operation="drafts.list",
        method="GET",
        path="/api/drafts",
        employee_id=employeeId,
    ) as op:
        result = svc.list_drafts(employeeId)
        op["count"] = len(result)
        return result


@router.post("", status_code=201)
def create_draft(payload: DraftCreate, svc: DraftService = Depends(get_draft_service)):
    """POST /drafts — save an incomplete ticket form."""
    with flow_operation(
        "drafts.create",
        operation="drafts.create",
        method="POST",
        path="/api/drafts",
        category=payload.category,
        priority=payload.priority,
    ) as op:
        result = svc.create_draft(
            employee_id=payload.employee_id,
            category=payload.category,
            subject=payload.subject,
            description=payload.description,
            priority=payload.priority,
        )
        op["draft_id"] = result.get("id")  # serialized draft: uuid (no TKT ref yet)
        op["employee_id"] = payload.employee_id
        return result


@router.get("/{draft_id}")
def get_draft(draft_id: str, employeeId: str, svc: DraftService = Depends(get_draft_service)):
    with flow_operation(
        "drafts.get",
        operation="drafts.get",
        method="GET",
        path=f"/api/drafts/{draft_id}",
        employee_id=employeeId,
    ) as op:
        op["draft_id"] = draft_id
        return svc.get_draft(draft_id, employeeId)


@router.patch("/{draft_id}")
def update_draft(
    draft_id: str,
    employeeId: str,
    payload: DraftUpdate,
    svc: DraftService = Depends(get_draft_service),
):
    patch = payload.model_dump(exclude_unset=True, exclude_none=True)
    # field NAMES only — the draft text itself must never reach a log
    patch_fields = sorted(patch)
    with flow_operation(
        "drafts.update",
        operation="drafts.update",
        method="PATCH",
        path=f"/api/drafts/{draft_id}",
        employee_id=employeeId,
        draft_id=draft_id,
        patch_fields=patch_fields,
    ):
        return svc.update_draft(draft_id, employeeId, patch)


@router.delete("/{draft_id}", status_code=STATUS_NO_BODY)
def delete_draft(draft_id: str, employeeId: str, svc: DraftService = Depends(get_draft_service)):
    with flow_operation(
        "drafts.delete",
        operation="drafts.delete",
        method="DELETE",
        path=f"/api/drafts/{draft_id}",
        employee_id=employeeId,
        draft_id=draft_id,
    ):
        svc.delete_draft(draft_id, employeeId)


@router.post("/{draft_id}/submit")
def submit_draft(
    draft_id: str, payload: DraftSubmit, svc: DraftService = Depends(get_draft_service)
):
    """Validate and convert the saved draft into a normal ticket."""
    with flow_operation(
        "drafts.submit",
        operation="drafts.submit",
        method="POST",
        path=f"/api/drafts/{draft_id}/submit",
        employee_id=payload.employee_id,
    ) as op:
        result = svc.submit_draft(draft_id, employee_id=payload.employee_id)
        op["draft_id"] = draft_id
        op["ticket_ref"] = result.get("id")  # the new TKT-ref
        return result


@router.post("/{draft_id}/attachment")
def upload_draft_attachment(
    draft_id: str,
    employeeId: str,
    file: UploadFile,
    svc: DraftService = Depends(get_draft_service),
):
    data = file.file.read()
    with flow_operation(
        "drafts.attachment.upload",
        operation="drafts.attachment_upload",
        method="POST",
        path=f"/api/drafts/{draft_id}/attachment",
        employee_id=employeeId,
        draft_id=draft_id,
        size_bytes=len(data),
        content_type=file.content_type,
    ):
        return svc.upload_attachment(
            draft_id,
            employeeId,
            filename=file.filename,
            content_type=file.content_type,
            data=data,
        )


@router.delete("/{draft_id}/attachment", status_code=STATUS_NO_BODY)
def delete_draft_attachment(
    draft_id: str,
    employeeId: str,
    svc: DraftService = Depends(get_draft_service),
):
    with flow_operation(
        "drafts.attachment.delete",
        operation="drafts.attachment_delete",
        method="DELETE",
        path=f"/api/drafts/{draft_id}/attachment",
        employee_id=employeeId,
        draft_id=draft_id,
    ):
        svc.delete_attachment(draft_id, employeeId)


@router.get("/{draft_id}/attachment")
def draft_attachment_url(
    draft_id: str,
    employeeId: str,
    request: Request,
    ttl: int = SIGNED_URL_TTL,
    svc: DraftService = Depends(get_draft_service),
):
    with flow_operation(
        "drafts.attachment.url",
        operation="drafts.attachment_url",
        method="GET",
        path=f"/api/drafts/{draft_id}/attachment",
        employee_id=employeeId,
        draft_id=draft_id,
    ) as event:
        result = svc.attachment_url(draft_id, employeeId, ttl)
        result["url"] = f"{str(request.base_url).rstrip('/')}{result['url']}"
        event["expires_in_seconds"] = result["expiresInSeconds"]
        return result
