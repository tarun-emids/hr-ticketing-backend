"""Notification domain: recipients, generic messages, emit, SLA sweep.

Design constraints (unchanged from the old app/notifications.py, now layered):
- Ticket writes stay decoupled from notification logic: every emit call is
  wrapped in safe_notify(), which swallows (and logs) any failure. A broken
  notification path can never break a ticket action.
- Rows are channel-agnostic (channel='in_app' today) so future channels can
  reuse the same store.
- Messages are generic on purpose — no ticket subject, description or reply
  body ever lands in a notification row (HR tickets are sensitive).
- Emission matrix: ticket_created -> all agents; ticket_assigned -> new
  assignee (skip re-picks, silence on unassign); ticket_status_changed ->
  owner + assignee minus actor; ticket_reply -> other party minus author
  (employee reply on an unassigned ticket fans out to all agents); SLA
  sweep -> all agents, at most once per ticket/threshold.

Observability: deliveries emit ``notification.deliver.started/completed/failed``
(hrdesk.flow) with the event TYPE, recipient count and ticket ref — inside
request context they carry the originating request id for free; in
background context they carry none (correct — jobs have no HTTP request).
Background jobs emit ``job.sla_sweep.*`` / ``job.retention_cleanup.*``
started/completed/failed with a per-run ``run_id`` (uuid4) and duration:
jobs have no HTTP request context, so a run id — not a fake request id —
identifies a sweep. Failures keep their full traceback via log.exception in
ADDITION to the structured failed event.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.observability import background_span, flow_event, new_run_id
from app.repositories.notification_repository import NotificationRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository

log = logging.getLogger("hrdesk.notifications")

EV_CREATED = "ticket_created"
EV_ASSIGNED = "ticket_assigned"
EV_STATUS = "ticket_status_changed"
EV_REPLY = "ticket_reply"
EV_SLA = "sla_breached"

SLA_THRESHOLDS_HOURS = {  # hours an unassigned ticket may wait for first contact
    "Urgent": 4,
    "default": 24,
}
SLA_SWEEP_INTERVAL_SECONDS = 1800
RETENTION_READ_DAYS = 30
RETENTION_UNREAD_DAYS = 180


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return now_utc().isoformat()


# ---------------------------------------------------------------------------
# Recipient rules (pure — no DB access, easy to unit test)
# ---------------------------------------------------------------------------


def created_recipients(agent_ids: list) -> list:
    """A new ticket informs every HR agent (the actor is the employee)."""
    return list(agent_ids)


def assigned_recipients(assignee_id, actor_id):
    """Assignment informs the new assignee only; assigning to yourself is a
    no-op and clearing an assignee notifies nobody."""
    if not assignee_id or assignee_id == actor_id:
        return []
    return [assignee_id]


def status_recipients(employee_id, assignee_id, actor_id):
    """A status change informs the owner and the assignee — never the actor."""
    ids = {employee_id}
    if assignee_id:
        ids.add(assignee_id)
    ids.discard(actor_id)
    return list(ids)


def reply_recipients(employee_id, assignee_id, author_id, author_role, agent_ids):
    """A reply informs the other party. Employee replies on still-unassigned
    tickets would otherwise reach nobody, so they fan out to agents."""
    ids = {employee_id}
    if assignee_id:
        ids.add(assignee_id)
    if assignee_id is None and author_role == "employee" and author_id == employee_id:
        ids.update(agent_ids)
    ids.discard(author_id)
    return list(ids)


def sla_threshold_hours(priority: str) -> int:
    return SLA_THRESHOLDS_HOURS.get(priority, SLA_THRESHOLDS_HOURS["default"])


# ---------------------------------------------------------------------------
# Message construction (pure)
# ---------------------------------------------------------------------------


def _ticket_ids(ticket: dict) -> tuple:
    """Emit callers pass either a raw DB row (id=uuid, ref='TKT-n') or an
    already-serialized ticket (id='TKT-n', uuid=uuid). Return (ref, uuid)."""
    if "ref" in ticket:
        return ticket["ref"], ticket["id"]
    return ticket.get("id"), ticket.get("uuid")


def _message_for(event: str, ticket: dict, actor_name, payload: dict) -> str:
    ref = _ticket_ids(ticket)[0] or "the ticket"
    if event == EV_CREATED:
        return f"New {ticket['category']} ticket {ref} filed by {actor_name}"
    if event == EV_ASSIGNED:
        if actor_name is None:
            return f"{ref} was assigned to you"
        return f"{actor_name} assigned {ref} to you"
    if event == EV_STATUS:
        status = payload.get("status", "")
        if status in ("Resolved", "Closed"):
            return f"{ref} was {status.lower()} by {actor_name}"
        if status in ("Open", "In Progress"):
            return f"{ref} was reopened — now {status}"
        who = f" by {actor_name}" if actor_name else ""
        return f"{ref} status is now {status}{who}"
    if event == EV_REPLY:
        return f"{actor_name} replied on {ref}"
    if event == EV_SLA:
        hours = payload.get("thresholdHours", SLA_THRESHOLDS_HOURS["default"])
        return f"{ref} is still unassigned after {hours} hours"
    return f"Update on {ref}"


def build_row(recipient_id: str, ticket: dict, event: str, actor_name, payload: dict) -> dict:
    """One stored notification row. Content is deliberately shallow."""
    ref, ticket_uuid = _ticket_ids(ticket)
    return {
        "recipient_id": recipient_id,
        "ticket_id": ticket_uuid,
        "ticket_ref": ref,
        "type": event,
        "channel": "in_app",
        "actor_name": actor_name,
        "payload": payload,
        "message": _message_for(event, ticket, actor_name, payload),
        "read": False,
        "created_at": _now_iso(),
    }


# ---------------------------------------------------------------------------
# Service: emit + background jobs
# ---------------------------------------------------------------------------


class NotificationService:
    """Emits notification rows and runs the two background jobs (SLA sweep,
    retention cleanup). Holds repositories only — safe to construct in any
    scope (request DI or the lifespan scheduler)."""

    def __init__(
        self,
        notifications: NotificationRepository,
        users: UserRepository,
        tickets: TicketRepository | None = None,
    ):
        self._notifications = notifications
        self._users = users
        self._tickets = tickets

    def agent_ids(self) -> list:
        """All HR agent user ids — fan-out targets for created/SLA events."""
        return self._users.agent_ids()

    def require_user(self, user_id: str) -> dict:
        """Edge guard used by every /notifications endpoint: the acting user
        must exist (mock-auth stand-in for a token in the final auth step)."""
        user = self._users.get_by_id(user_id)
        if not user:
            raise HTTPException(status_code=422, detail="userId does not match a known user")
        return user

    # -- reads (hard-scoped to the acting user) ------------------------------

    @staticmethod
    def _notification_out(row: dict) -> dict:
        """Exact camelCase notification row shape the frontend displays."""
        return {
            "id": row["id"],
            "recipientId": row["recipient_id"],
            "ticketId": row.get("ticket_id"),
            "ticketRef": row.get("ticket_ref"),
            "type": row["type"],
            "channel": row["channel"],
            "actorName": row.get("actor_name"),
            "payload": row.get("payload", {}),
            "message": row.get("message", ""),
            "read": bool(row["read"]),
            "readAt": row.get("read_at"),
            "createdAt": row["created_at"],
        }

    def list_notifications(
        self, user_id: str, *, unread_only: bool, limit: int, offset: int
    ) -> list[dict]:
        """Newest-first page for one user (chronological, not unread-first)."""
        rows = self._notifications.list_for_recipient(
            user_id, unread_only=unread_only, fetch_limit=limit, offset=offset
        )
        return [self._notification_out(r) for r in rows]

    def unread_count(self, user_id: str) -> int:
        return len(self._notifications.unread_rows(user_id))

    def mark_all_read(self, user_id: str) -> int:
        return len(self._notifications.mark_all_read(user_id, _now_iso()))

    def mark_read(self, notification_id: str, user_id: str) -> dict:
        rows = self._notifications.mark_read(notification_id, user_id, _now_iso())
        if not rows:
            raise HTTPException(status_code=404, detail="Notification not found")
        return self._notification_out(rows[0])

    # -- emit ---------------------------------------------------------------

    def emit(
        self,
        ticket: dict,
        event: str,
        actor: dict | None,
        recipient_ids: list,
        payload: dict | None = None,
    ) -> int:
        """Persist notifications for one event. Raises on DB failure — callers
        that must never break a ticket action use safe_notify() instead."""
        actor_name = (actor or {}).get("name")
        full_payload = {"actorId": (actor or {}).get("id"), **(payload or {})}
        rows = [
            build_row(rid, ticket, event, actor_name, full_payload)
            for rid in sorted(set(filter(None, recipient_ids)))
        ]
        if not rows:
            return 0
        self._notifications.insert_rows(rows)
        return len(rows)

    def safe_notify(
        self,
        ticket: dict,
        event: str,
        actor: dict | None,
        recipient_ids: list,
        payload: dict | None = None,
    ) -> None:
        """Fail-safe emit: a notification failure must never break a ticket
        action. The structured deliver events carry safe metadata only —
        event TYPE, recipient count, ticket ref (no notification rows'
        recipient ids here; delivery details stay in the DB rows)."""
        ref = _ticket_ids(ticket)[0]
        count = len(sorted(set(filter(None, recipient_ids))))
        flow_event(
            "notification.deliver.started",
            operation="notifications.emit",
            event_type=event,
            recipient_count=count,
            ticket_ref=ref,
        )
        try:
            delivered = self.emit(ticket, event, actor, recipient_ids, payload)
            flow_event(
                "notification.deliver.completed",
                operation="notifications.emit",
                delivered=delivered,
            )
        except Exception as exc:
            flow_event(
                "notification.deliver.failed",
                operation="notifications.emit",
                error=type(exc).__name__,
            )
            log.exception("notification emit failed (event=%s ticket=%s)", event, ref)

    # -- background job 1: first-response SLA sweep --------------------------

    def run_sla_sweep(self) -> int:
        """Notify every agent about unassigned tickets past their first-response
        SLA (Urgent: 4h, else 24h). Each ticket/threshold notifies at most once.
        A failing sweep only logs — background jobs must not crash the app."""
        run_id = new_run_id()  # jobs have no HTTP request context; run id, not request id
        started = time.perf_counter()
        try:
            with background_span("hrdesk.jobs.sla_sweep") as span:
                flow_event("job.sla_sweep.started", operation="jobs.sla_sweep", run_id=run_id)
                notified = self._run_sla_sweep_inner()
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                if span is not None and span.is_recording():
                    span.set_attribute("hrdesk.notified", notified)
                    span.set_attribute("hrdesk.run_id", run_id)
                flow_event(
                    "job.sla_sweep.completed",
                    operation="jobs.sla_sweep",
                    run_id=run_id,
                    notified=notified,
                    duration_ms=duration_ms,
                )
                return notified
        except Exception as exc:
            flow_event(
                "job.sla_sweep.failed",
                operation="jobs.sla_sweep",
                run_id=run_id,
                error=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            log.exception("SLA sweep failed")
            return 0

    def _run_sla_sweep_inner(self) -> int:
        agents = self.agent_ids()
        now = now_utc()
        triggered = 0
        for row in self._tickets.unassigned_by_statuses(("Open", "In Progress")):
            threshold_h = sla_threshold_hours(row["priority"])
            created_value = row["created_at"]
            if isinstance(created_value, str):
                created = datetime.fromisoformat(created_value.replace("Z", "+00:00"))
            else:
                created = created_value
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            if now - created < timedelta(hours=threshold_h):
                continue
            if threshold_h in self._notifications.prior_sla_thresholds(row["id"]):
                continue
            self.safe_notify(row, EV_SLA, None, agents, payload={"thresholdHours": threshold_h})
            triggered += 1
        return triggered

    # -- background job 2: retention cleanup ---------------------------------

    def run_retention_cleanup(self) -> int:
        """Delete read notifications older than 30 days and everything older
        than 180 days. Returns the number of rows deleted; failures only log."""
        run_id = new_run_id()
        started = time.perf_counter()
        try:
            with background_span("hrdesk.jobs.retention_cleanup") as span:
                flow_event(
                    "job.retention_cleanup.started",
                    operation="jobs.retention_cleanup",
                    run_id=run_id,
                )
                deleted = self._run_retention_cleanup_inner()
                duration_ms = round((time.perf_counter() - started) * 1000, 1)
                if span is not None and span.is_recording():
                    span.set_attribute("hrdesk.deleted", deleted)
                    span.set_attribute("hrdesk.run_id", run_id)
                flow_event(
                    "job.retention_cleanup.completed",
                    operation="jobs.retention_cleanup",
                    run_id=run_id,
                    deleted=deleted,
                    duration_ms=duration_ms,
                )
                return deleted
        except Exception as exc:
            flow_event(
                "job.retention_cleanup.failed",
                operation="jobs.retention_cleanup",
                run_id=run_id,
                error=type(exc).__name__,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
            log.exception("retention cleanup failed")
            return 0

    def _run_retention_cleanup_inner(self) -> int:
        read_cutoff = (now_utc() - timedelta(days=RETENTION_READ_DAYS)).isoformat()
        any_cutoff = (now_utc() - timedelta(days=RETENTION_UNREAD_DAYS)).isoformat()

        doomed: set = set()
        for r in self._notifications.ids_of_read_older_than(read_cutoff):
            doomed.add(r["id"])
        for r in self._notifications.ids_of_any_older_than(any_cutoff):
            doomed.add(r["id"])

        deleted = 0
        for nid in doomed:
            self._notifications.delete_row(nid)
            deleted += 1
        return deleted
