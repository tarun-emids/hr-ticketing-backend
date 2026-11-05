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

from app.models import ACTIVE_STATUSES, ticket_out
from app.observability import flow_event
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.repositories.base import UUID_RE, as_uuid
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

AGENT_PICKUP_TEXT = "Thanks for raising this — I've picked it up and will get back to you shortly."

_SORT_KEYS = frozenset({"updated", "created", "priority", "subject", "status", "employee"})
_ORDER_KEYS = frozenset({"asc", "desc"})


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

    def _patch_and_return(self, tid: str, patch: dict, *, operation: Optional[str] = None) -> dict:
        """Patch the ticket row (trigger bumps updated_at), return the full ticket."""
        row = self._row(tid)
        if operation is None:
            self._tickets.update_ticket(row["id"], patch)
        else:
            self._tickets.update_ticket(row["id"], patch, operation=operation)
        return self._full(tid)

    def require_viewer(self, viewer_id: Optional[str]) -> dict:
        """Edge guard for ticket reads: viewerId must resolve to a real
        account row before any visibility decision. Malformed: 422; unknown:
        404 (require_account semantics, so 'bad request' and 'no such
        account' answer differently on purpose)."""
        if not viewer_id or not isinstance(viewer_id, str) or not UUID_RE.match(viewer_id):
            raise HTTPException(status_code=422, detail="viewerId (uuid) is required")
        viewer = self._users.get_by_id(viewer_id)
        if not viewer:
            raise HTTPException(status_code=404, detail="Unknown viewer")
        return viewer

    @staticmethod
    def _list_scope(viewer: dict) -> Optional[uuidlib.UUID]:
        """Mandatory visibility predicate for ticket-list reads, derived from
        the RESOLVED viewer row. employee -> exactly this person's tickets
        (employee_id = viewer id); agent/admin -> None (unrestricted). The
        repository receives the predicate, never the role."""
        if viewer.get("role") == "employee":
            return as_uuid(viewer["id"])
        return None

    def _require_viewable(self, row: dict, viewer: dict, *, action: str = "view") -> None:
        """Detail gate. Reuses _list_scope as the SINGLE source of truth for
        "which roles are restricted": a restricted viewer may open only
        tickets in their scope; KB-style 403 (known to exist, not for this
        viewer) rather than 404. Note the check reads the resolved viewer and
        the fetched row — no client claim participates."""
        scoped_id = self._list_scope(viewer)
        if scoped_id is not None and scoped_id != as_uuid(row["employee_id"]):
            raise HTTPException(status_code=403, detail=f"Not allowed to {action} this ticket.")

    STAFF_ROLES = frozenset({"agent", "admin"})

    def require_staff(self, viewer: dict) -> None:
        """Staff-only operations: assignment, classification, auto-routing,
        workload. Restricted roles answer 403 before any ticket query for the
        operation begins — existence is never tested for a claim that cannot
        act. Restricted set: RESTRICTED_TICKET_ROLES (same class, read side);
        new roles added later default to neither, i.e. non-staff."""
        if viewer.get("role") not in self.STAFF_ROLES:
            raise HTTPException(status_code=403, detail="Not allowed: HR staff or admin only.")

    # -- reads --------------------------------------------------------------

    def get(self, tid: str, *, viewer: dict) -> dict:
        """GET /tickets/{TKT-123 | uuid} — full ticket incl. thread, gated by
        the server-resolved viewer."""
        row = self._row(tid)
        self._require_viewable(row, viewer)
        return ticket_out(row, self._tickets.list_replies(row["id"]))

    def list_paged(
        self,
        *,
        viewer: dict,
        page: int,
        page_size: int,
        sort: str = "updated",
        order: str = "desc",
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        employee_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        q: Optional[str] = None,
        unassigned: bool = False,
    ) -> dict:
        if sort not in _SORT_KEYS or order not in _ORDER_KEYS:
            raise HTTPException(
                status_code=422,
                detail=f"sort must be one of {sorted(_SORT_KEYS)}; order must be asc or desc",
            )
        """Paginated ticket list: one validated page + exact total. Shares the
        scope rule with list(); count_filtered shares the same filter tuple,
        so total and items prove to agree with each other by construction."""
        scope = self._list_scope(viewer)
        rows = self._tickets.list_filtered(
            employee_scope_id=scope,
            sort=sort,
            order=order,
            status=status,
            category=category,
            priority=priority,
            employee_id=employee_id,
            assignee_id=assignee_id,
            q=q,
            unassigned=unassigned,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        total = self._tickets.count_filtered(
            employee_scope_id=scope,
            status=status,
            category=category,
            priority=priority,
            employee_id=employee_id,
            assignee_id=assignee_id,
            q=q,
            unassigned=unassigned,
        )
        return {
            "items": [ticket_out(r, []) for r in rows],
            "page": page,
            "pageSize": page_size,
            "total": total,
            "hasNext": page * page_size < total,
        }

    def agent_workload(self) -> list[dict]:
        """GET /agents/workload — per-agent open/total ticket counts.

        One GROUP BY aggregate in the repository keyed by assignee; the
        agent roster supplies ordering (account creation date) and the
        zero-count defaults via the same [0, 0] schema as before. No
        viewer data participates, so no per-viewer keying exists."""
        agents = self._users.agents()
        counts = {
            row["agent_id"]: [row["open_count"], row["total_count"]]
            for row in self._tickets.count_by_assignee(ACTIVE_STATUSES)
        }
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
        new_row = self._tickets.insert_ticket(row, operation="tickets.create")
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
        Restricted (employee) author may reply only on their own ticket.
        """
        row = self._row(tid)
        author = self._users.get_by_id(author_id)
        if not author:
            raise HTTPException(status_code=422, detail="authorId does not match a known user")
        self._require_viewable(row, author, action="reply to")
        role = author["role"]
        flow_event(
            "ticket.service.validation_completed",
            operation="tickets.reply",
            author_id=author_id,
            author_role=role,
        )

        now = self._now()
        self._tickets.insert_reply(
            {
                "ticket_id": row["id"],
                "author_id": author_id,
                "author_role": role,
                "body": text.strip(),
            },
            operation="tickets.reply",
        )

        patch: dict = {}
        if role == "agent":
            if not row.get("first_reply_at"):
                patch["first_reply_at"] = now
            if row["status"] == "Open":
                patch["status"] = "In Progress"
        elif role == "employee" and row["status"] not in ("Resolved", "Closed"):
            patch["status"] = "Waiting on Employee"

        if patch:
            self._tickets.update_ticket(row["id"], patch, operation="tickets.reply")
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
        stamps closedBy, reopening clears both. Restricted (employee) actor
        may transition only their own ticket."""
        row = self._row(tid)

        actor = self._users.get_by_id(actor_id)
        if not actor:
            raise HTTPException(status_code=422, detail="actorId does not match a known user")
        self._require_viewable(row, actor, action="modify")
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
        result = self._patch_and_return(tid, patch, operation="tickets.status")
        self._notifier.safe_notify(
            result,
            EV_STATUS,
            actor,
            status_recipients(row["employee_id"], row.get("assignee_id"), actor["id"]),
            payload={"status": status},
        )
        return result

    def set_priority(self, tid: str, priority: str) -> dict:
        return self._patch_and_return(tid, {"priority": priority}, operation="tickets.priority")

    def set_category(self, tid: str, category: str) -> dict:
        return self._patch_and_return(tid, {"category": category}, operation="tickets.category")

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

        # Capture before updating so the reassignment decision cannot depend
        # on state written by our own update.
        pre_assignee = row.get("assignee_id")
        has_agent_turn = self._tickets.has_agent_reply(row["id"])

        now = self._now()
        if assignee_id and not row.get("first_reply_at") and not has_agent_turn:
            self._tickets.insert_reply(
                {
                    "ticket_id": row["id"],
                    "author_id": assignee_id,
                    "author_role": "agent",
                    "body": AGENT_PICKUP_TEXT,
                },
                operation="tickets.assign",
            )
            patch: dict = {"assignee_id": assignee_id, "first_reply_at": now}
            if row["status"] == "Open":
                patch["status"] = "In Progress"
            result = self._patch_and_return(row["ref"], patch, operation="tickets.assign")
        else:
            result = self._patch_and_return(
                row["ref"], {"assignee_id": assignee_id}, operation="tickets.assign"
            )

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
        self,
        tid: str,
        *,
        filename: str | None,
        content_type: str | None,
        data: bytes,
        viewer: dict,
    ) -> dict:
        """POST /tickets/{id}/attachment — one file per ticket (re-upload
        replaces the previous attachment), <=5 MB."""
        if not filename:
            raise HTTPException(status_code=422, detail="No file provided")

        row = self._row(tid)  # 404 beats 413 — check existence before storage
        self._require_viewable(row, viewer, action="modify")
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

        updated = self._patch_and_return(
            tid,
            {
                "attachment_path": path,
                "attachment_name": filename,
                "attachment_size": len(data),
            },
            operation="tickets.attachment_upload",
        )
        if row.get("attachment_path"):
            self._storage.remove(row["attachment_path"])
        return updated

    def attachment_url(self, tid: str, ttl: int, *, viewer: dict) -> dict:
        """GET /tickets/{id}/attachment — short-lived signed URL for the file.
        The URL itself (one-time token) is deliberately never logged."""
        row = self._row(tid)
        self._require_viewable(row, viewer)
        if not row.get("attachment_path"):
            raise HTTPException(status_code=404, detail="Ticket has no attachment")

        url = self._storage.signed_url(row["attachment_path"], ttl)
        flow_event(
            "attachment.storage.url_signed",
            operation="tickets.attachment_url",
            ticket_ref=row.get("ref"),
            expires_in_seconds=self._storage.clamp_ttl(ttl),
        )
        return {
            "name": row.get("attachment_name"),
            "size": row.get("attachment_size"),
            "url": url,
            "expiresInSeconds": self._storage.clamp_ttl(ttl),
        }
