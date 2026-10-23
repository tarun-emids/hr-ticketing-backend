"""Employee ticket drafts and their optional attachments.

Drafts are strictly employee-owned: every operation re-scopes by
employee_id server-side, so an employee can never see or submit someone
else's draft. submit converts a draft into a normal ticket (running the same
validation the create endpoint enforces) and deletes the draft.

Observability: controller events (``drafts.*`` started/completed/failed)
frame each operation; this layer adds the milestones that matter:
``draft.service.validation_completed`` after ownership + submit validation,
``attachment.storage.upload_completed`` for draft attachment uploads.
Errors propagate unchanged (classified at the controller boundary). No
draft text, file names or signed URLs are ever logged.
"""

import os
import uuid as uuidlib

from fastapi import HTTPException

from app.models import draft_out, ticket_out
from app.observability import flow_event
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.repositories.draft_repository import DraftRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.notification_service import EV_CREATED, NotificationService, created_recipients


class DraftService:
    def __init__(
        self,
        drafts: DraftRepository,
        tickets: TicketRepository,
        users: UserRepository,
        storage: AttachmentStorageRepository,
        notifier: NotificationService,
    ):
        self._drafts = drafts
        self._tickets = tickets
        self._users = users
        self._storage = storage
        self._notifier = notifier

    # -- guards ---------------------------------------------------------------

    def _verify_employee(self, employee_id: str) -> dict:
        employee = self._users.get_by_id(employee_id)
        if not employee or employee["role"] != "employee":
            raise HTTPException(
                status_code=422, detail="employeeId must belong to a known employee"
            )
        return employee

    def _owned_draft(self, draft_id: str, employee_id: str) -> dict:
        draft = self._drafts.get_owned(draft_id, employee_id)
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        return draft

    # -- CRUD -----------------------------------------------------------------

    def list_drafts(self, employee_id: str) -> list[dict]:
        """GET /drafts?employeeId=... — drafts belonging to one employee."""
        self._verify_employee(employee_id)
        return [draft_out(row) for row in self._drafts.list_for_employee(employee_id)]

    def create_draft(
        self, *, employee_id: str, category: str, subject: str, description: str, priority: str
    ) -> dict:
        """POST /drafts — save an incomplete ticket form."""
        self._verify_employee(employee_id)
        saved = self._drafts.insert_draft(
            {
                "employee_id": employee_id,
                "category": category,
                "subject": subject.strip(),
                "description": description.strip(),
                "priority": priority,
            }
        )
        return draft_out(saved)

    def get_draft(self, draft_id: str, employee_id: str) -> dict:
        return draft_out(self._owned_draft(draft_id, employee_id))

    def update_draft(self, draft_id: str, employee_id: str, patch_fields: dict) -> dict:
        row = self._owned_draft(draft_id, employee_id)
        patch = dict(patch_fields)
        for field in ("subject", "description"):
            if field in patch:
                patch[field] = patch[field].strip()
        if patch:
            self._drafts.update_draft(row["id"], patch)
        return draft_out(self._owned_draft(draft_id, employee_id))

    def delete_draft(self, draft_id: str, employee_id: str) -> None:
        row = self._owned_draft(draft_id, employee_id)
        if row.get("attachment_path"):
            self._storage.remove(row["attachment_path"])
        self._drafts.delete_draft(row["id"])

    # -- submit -----------------------------------------------------------------

    def submit_draft(self, draft_id: str, *, employee_id: str) -> dict:
        """Validate and convert the saved draft into a normal ticket."""
        draft = self._owned_draft(draft_id, employee_id)
        employee = self._verify_employee(employee_id)
        subject = draft["subject"].strip()
        description = draft["description"].strip()
        if len(subject) < 5:
            raise HTTPException(status_code=422, detail="Subject needs at least 5 characters.")
        if len(description) < 20:
            raise HTTPException(status_code=422, detail="Description needs at least 20 characters.")
        flow_event(
            "draft.service.validation_completed",
            operation="drafts.submit",
            draft_id=draft_id,
            category=draft["category"],
            priority=draft["priority"],
            has_attachment=bool(draft.get("attachment_path")),
        )

        ticket = self._tickets.insert_ticket(
            {
                "employee_id": employee_id,
                "category": draft["category"],
                "subject": subject,
                "description": description,
                "priority": draft["priority"],
                "status": "Open",
                "attachment_path": draft.get("attachment_path"),
                "attachment_name": draft.get("attachment_name"),
                "attachment_size": draft.get("attachment_size"),
            },
            operation="drafts.submit",
        )
        self._drafts.delete_draft(draft["id"])
        self._notifier.safe_notify(
            ticket, EV_CREATED, employee, created_recipients(self._notifier.agent_ids())
        )
        return ticket_out(ticket, [])

    # -- draft attachments --------------------------------------------------------

    def _unique_path(self, draft_id: str, filename: str | None) -> str:
        ext = os.path.splitext(filename or "")[1][:16] or ".bin"
        return f"drafts/{draft_id}/{uuidlib.uuid4().hex}{ext}"

    def upload_attachment(
        self,
        draft_id: str,
        employee_id: str,
        filename: str | None,
        content_type: str | None,
        data: bytes,
    ) -> dict:
        if not filename:
            raise HTTPException(status_code=422, detail="No file provided")
        draft = self._owned_draft(draft_id, employee_id)
        self._storage.check_size(data)

        path = self._unique_path(draft_id, filename)
        self._storage.upload(path, data, content_type)
        # Storage milestone: size/type/path only — filename + bytes never logged.
        flow_event(
            "attachment.storage.upload_completed",
            operation="drafts.attachment_upload",
            size_bytes=len(data),
            content_type=content_type,
            storage_path=path,
            draft_id=draft_id,
        )

        self._drafts.update_draft(
            draft["id"],
            {
                "attachment_path": path,
                "attachment_name": filename,
                "attachment_size": len(data),
            },
        )
        if draft.get("attachment_path"):
            self._storage.remove(draft["attachment_path"])
        return draft_out(self._owned_draft(draft_id, employee_id))

    def delete_attachment(self, draft_id: str, employee_id: str) -> None:
        draft = self._owned_draft(draft_id, employee_id)
        if draft.get("attachment_path"):
            self._storage.remove(draft["attachment_path"])
            self._drafts.update_draft(
                draft["id"],
                {
                    "attachment_path": None,
                    "attachment_name": None,
                    "attachment_size": None,
                },
            )

    def attachment_url(self, draft_id: str, employee_id: str, ttl: int) -> dict:
        draft = self._owned_draft(draft_id, employee_id)
        if not draft.get("attachment_path"):
            raise HTTPException(status_code=404, detail="Draft has no attachment")
        url = self._storage.signed_url(draft["attachment_path"], ttl)
        flow_event(
            "attachment.storage.url_signed",
            operation="drafts.attachment_url",
            draft_id=draft_id,
            expires_in_seconds=self._storage.clamp_ttl(ttl),
        )
        return {
            "name": draft.get("attachment_name"),
            "size": draft.get("attachment_size"),
            "url": url,
            "expiresInSeconds": self._storage.clamp_ttl(ttl),
        }
