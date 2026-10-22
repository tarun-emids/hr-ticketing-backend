"""Ticket service — CRUD, thread (replies), lifecycle and assignment.

Mirrors src/data/store.js 1:1 (same rules the frontend mock enforces):

- agent reply stamps firstReplyAt (once) and moves Open -> In Progress;
- employee reply flips a non-final ticket to Waiting on Employee;
- assigning an unanswered ticket also posts the agent pickup reply, stamps
  firstReplyAt and moves Open -> In Progress (shared by manual PATCH
  /assignee AND auto-assign);
- Resolved stamps resolvedAt; Closed also records closedBy; reopening
  (Open / In Progress) clears both;
- auto-assign routes to the least-loaded agent (open count, total as
  tiebreak). Pure counting — no AI, no scoring, fully inspectable.

Observability: controller events (``tickets.*`` started/completed/failed
via flow_operation) trace the outer boundary; this layer adds milestones at
points a developer would otherwise have to infer: validation after guard
checks (``ticket.service.validation_completed``), the auto-assign decision
(``ticket.service.assignment_selected``), and storage milestones for
attachments (``attachment.storage.upload_completed`` /
``attachment.storage.url_signed`` — URLs/names never logged). Errors keep
propagating unchanged; failure classification lives at the controller
boundary.
"""

import os
import uuid as uuidlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.config import SIGNED_URL_TTL
from app.models import ticket_out
from app.observability import flow_event
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.notification_service import (
    EV_ASSIGNED,
    EV_CREATED,
    EV_REPLY,
    EV_STATUS,
    NotificationService,
    assigned_recipients,
    created_recipients,
    reply_recipients,
    status_recipients,
)

ACTIVE_STATUSES = ("Open", "In Progress", "Waiting on Employee")

AGENT_PICKUP_TEXT = "Thanks for raising this — I've picked it up and will get back to you shortly."


class TicketNotFound(HTTPException):
    def __init__(self, detail: str = "Ticket not found"):
        super().__init__(status_code=404, detail=detail)


class TicketService:
    def __init__(
        self,
        tickets: TicketRepository,
        users: UserRepository,
        notifier: NotificationService,
        storage: AttachmentStorageRepository,
    ):
        self._tickets = tickets
        self._users = users
        self._notifier = notifier
        self._storage = storage

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row(self, tid: str) -> dict:
        row = self._tickets.get_by_key(tid)
        if not row:
            raise TicketNotFound()
        return row

    def _full(self, tid: str) -> dict:
        row = self._row(tid)
        return ticket_out(row, self._tickets.list_replies(row["id"]))

    def _patch_and_return(self, tid: str, patch: dict) -> dict:
        """Patch the ticket row (trigger bumps updated_at), return the full ticket."""
        row = self._row(tid)
        self._tickets.update_ticket(row["id"], patch)
        return self._full(tid)

    # -- reads --------------------------------------------------------------

    def get(self, tid: str) -> dict:
        """GET /tickets/{TKT-123 | uuid} — full ticket incl. thread."""
        return self._full(tid)

    def list(
        self,
        *,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        employee_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        q: Optional[str] = None,
        unassigned: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        """GET /tickets — newest-first by updatedAt (list items carry empty
        turns; load a single ticket for the full thread)."""
        rows = self._tickets.list_filtered(
            status=status,
            category=category,
            priority=priority,
            employee_id=employee_id,
            assignee_id=assignee_id,
            q=q,
            unassigned=unassigned,
            limit=limit,
        )
        return [ticket_out(r, []) for r in rows]

    def agent_workload(self) -> list[dict]:
        """GET /agents/workload — per-agent open/total ticket counts.

        Single lightweight scan; aggregate in Python (v2: no .not_ chains
        needed). Agents ordered by account creation date."""
        agents = self._users.agents()
        scan = self._tickets.scan_assignee_status(2000)
        counts: dict[str, list[int]] = {}  # id -> [open, total]
        for t in scan:
            assignee = t.get("assignee_id")
            if not assignee:
                continue
            entry = counts.setdefault(assignee, [0, 0])
            entry[1] += 1
            if t["status"] in ACTIVE_STATUSES:
                entry[0] += 1

        return [
            {
                "id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "openCount": counts.get(u["id"], [0, 0])[0],
                "totalCount": counts.get(u["id"], [0, 0])[1],
            }
            for u in agents
        ]

    # -- create -------------------------------------------------------------

    def create(
        self, *, employee_id: str, category: str, subject: str, description: str, priority: str
    ) -> dict:
        """POST /tickets — create a ticket (guards: employee exists + role check)."""
        employee = self._users.get_by_id(employee_id)
        if not employee:
            raise HTTPException(status_code=422, detail="employeeId does not match a known user")
        if employee["role"] != "employee":
            raise HTTPException(
                status_code=422,
                detail="employeeId must belong to a user with role 'employee'",
            )
        # Guards passed — no ticket content below; only safe metadata.
        flow_event(
            "ticket.service.validation_completed",
            operation="tickets.create",
            employee_id=employee_id,
            category=category,
            priority=priority,
        )

        row = {
            "employee_id": employee_id,
            "category": category,
            "subject": subject.strip(),
            "description": description.strip(),
            "priority": priority,
            "status": "Open",
        }
        new_row = self._tickets.insert_ticket(row)
        # Notify AFTER the insert; safe_notify swallows any notification failure.
        self._notifier.safe_notify(
            new_row, EV_CREATED, employee, created_recipients(self._notifier.agent_ids())
        )
        return ticket_out(new_row, [])

    # -- replies ------------------------------------------------------------

    def add_reply(self, tid: str, *, author_id: str, text: str) -> dict:
        """POST /tickets/{id}/replies — store.js addReply parity.

        Agent reply: stamps firstReplyAt (once) and Open -> In Progress.
        Employee reply: non-final statuses flip to Waiting on Employee.
        """
        row = self._row(tid)
        author = self._users.get_by_id(author_id)
        if not author:
            raise HTTPException(status_code=422, detail="authorId does not match a known user")
        role = author["role"]
        flow_event(
            "ticket.service.validation_completed",
            operation="tickets.reply",
            author_id=author_id,
            author_role=role,
        )

        now = self._now()
        self._tickets.insert_reply({
            "ticket_id": row["id"],
            "author_id": author_id,
            "author_role": role,
            "body": text.strip(),
        }, operation="tickets.reply")

        patch: dict = {}
        if role == "agent":
            if not row.get("first_reply_at"):
                patch["first_reply_at"] = now
            if row["status"] == "Open":
                patch["status"] = "In Progress"
        elif role == "employee" and row["status"] not in ("Resolved", "Closed"):
            patch["status"] = "Waiting on Employee"

        if patch:
            self._tickets.update_ticket(row["id"], patch)
        self._notifier.safe_notify(
            row,
            EV_REPLY,
            author,
            reply_recipients(
                row["employee_id"],
                row.get("assignee_id"),
                author["id"],
                author["role"],
                self._notifier.agent_ids(),
            ),
        )
        return self._full(tid)

    # -- lifecycle ----------------------------------------------------------

    def update_status(self, tid: str, *, status: str, actor_id: str) -> dict:
        """store.js updateStatus parity: Resolved stamps resolvedAt, Closed also
        stamps closedBy, reopening clears both."""
        row = self._row(tid)

        actor = self._users.get_by_id(actor_id)
        if not actor:
            raise HTTPException(status_code=422, detail="actorId does not match a known user")
        flow_event(
            "ticket.service.validation_completed",
            operation="tickets.status",
            actor_id=actor_id,
            from_status=row.get("status"),
            to_status=status,
        )

        patch: dict = {"status": status}
        if status == "Resolved":
            patch["resolved_at"] = self._now()
        elif status == "Closed":
            patch["resolved_at"] = row.get("resolved_at") or self._now()
            patch["closed_by"] = actor_id
        elif status in ("Open", "In Progress"):
            patch["resolved_at"] = None
            patch["closed_by"] = None
        # Waiting on Employee: no timestamp changes
        result = self._patch_and_return(tid, patch)
        self._notifier.safe_notify(
            result,
            EV_STATUS,
            actor,
            status_recipients(row["employee_id"], row.get("assignee_id"), actor["id"]),
            payload={"status": status},
        )
        return result

    def set_priority(self, tid: str, priority: str) -> dict:
        return self._patch_and_return(tid, {"priority": priority})

    def set_category(self, tid: str, category: str) -> dict:
        return self._patch_and_return(tid, {"category": category})

    # -- assignment ---------------------------------------------------------

    def assign(self, row: dict, assignee_id: Optional[str]) -> dict:
        """Core assignment flow (manual + auto both land here).

        store.js assignTicket parity: assigning an unanswered ticket also
        posts the agent pickup reply, sets firstReplyAt, and moves
        Open -> In Progress.
        """
        if assignee_id:
            agent = self._users.get_by_id(assignee_id)
            if not agent:
                raise HTTPException(
                    status_code=422, detail="assigneeId does not match a known user"
                )
            if agent["role"] != "agent":
                raise HTTPException(status_code=422, detail="assigneeId must be an HR agent")
            flow_event(
                "ticket.service.validation_completed",
                operation="tickets.assign",
                assignee_id=assignee_id,
            )

        # Capture the PRE-update assignee: the decision "is this an actual
        # reassignment" must not depend on state written by our own update
        # (PostgREST returns snapshots, but the comparison itself is clearer
        # and unsafe-alias-proof when captured before the patch).
        pre_assignee = row.get("assignee_id")
        has_agent_turn = self._tickets.has_agent_reply(row["id"])

        now = self._now()
        if assignee_id and not row.get("first_reply_at") and not has_agent_turn:
            self._tickets.insert_reply({
                "ticket_id": row["id"],
                "author_id": assignee_id,
                "author_role": "agent",
                "body": AGENT_PICKUP_TEXT,
            }, operation="tickets.assign")
            patch: dict = {"assignee_id": assignee_id, "first_reply_at": now}
            if row["status"] == "Open":
                patch["status"] = "In Progress"
            result = self._patch_and_return(row["ref"], patch)
        else:
            result = self._patch_and_return(row["ref"], {"assignee_id": assignee_id})

        if pre_assignee != assignee_id:
            self._notifier.safe_notify(
                row, EV_ASSIGNED, None, assigned_recipients(assignee_id, None)
            )
        return result

    def assign_by_key(self, tid: str, assignee_id: Optional[str]) -> dict:
        """PATCH /tickets/{id}/assignee — resolve TKT-ref/uuid key, then flow."""
        return self.assign(self._row(tid), assignee_id)

    def auto_assign(self, tid: str) -> dict:
        """Route a ticket to the least-loaded HR agent."""
        row = self._row(tid)
        if row["status"] in ("Resolved", "Closed"):
            raise HTTPException(
                status_code=409,
                detail=f"Ticket {row['ref']} is {row['status']}; reopen it before assigning.",
            )

        plate = self.agent_workload()
        if not plate:
            raise HTTPException(status_code=409, detail="No HR agents are configured yet.")

        pick = min(plate, key=lambda a: (a["openCount"], a["totalCount"]))
        flow_event(
            "ticket.service.assignment_selected",
            operation="tickets.auto_assign",
            routed_to=pick["id"],
            agent_open_count=pick["openCount"],
            agent_total_count=pick["totalCount"],
            candidates=len(plate),
        )
        ticket = self.assign(row, pick["id"])
        return {
            **ticket,
            "routedTo": {"id": pick["id"], "name": pick["name"], "openCount": pick["openCount"]},
        }

    # -- attachments ---------------------------------------------------------

    def upload_attachment(
        self, tid: str, *, filename: str | None, content_type: str | None, data: bytes
    ) -> dict:
        """POST /tickets/{id}/attachment — one file per ticket (re-upload
        replaces the previous attachment), <=5 MB."""
        if not filename:
            raise HTTPException(status_code=422, detail="No file provided")

        row = self._row(tid)  # 404 beats 413 — check existence before storage
        self._storage.check_size(data)

        ext = os.path.splitext(filename)[1][:16] or ".bin"
        path = f"{row['ref']}/{uuidlib.uuid4().hex}{ext}"
        self._storage.upload(path, data, content_type)
        # Storage milestone: size/type/path only — filename + bytes never logged.
        flow_event(
            "attachment.storage.upload_completed",
            operation="tickets.attachment_upload",
            size_bytes=len(data),
            content_type=content_type,
            storage_path=path,
            ticket_ref=row.get("ref"),
        )

        return self._patch_and_return(
            tid,
            {
                "attachment_path": path,
                "attachment_name": filename,
                "attachment_size": len(data),
            },
        )

    def attachment_url(self, tid: str, ttl: int) -> dict:
        """GET /tickets/{id}/attachment — short-lived signed URL for the file.
        The URL itself (one-time token) is deliberately never logged."""
        row = self._row(tid)
        if not row.get("attachment_path"):
            raise HTTPException(status_code=404, detail="Ticket has no attachment")

        url = self._storage.signed_url(row["attachment_path"], ttl)
        flow_event(
            "attachment.storage.url_signed",
            operation="tickets.attachment_url",
            ticket_ref=row.get("ref"),
            expires_in_seconds=SIGNED_URL_TTL,
        )
        return {
            "name": row.get("attachment_name"),
            "size": row.get("attachment_size"),
            "url": url,
            "expiresInSeconds": SIGNED_URL_TTL,
        }
