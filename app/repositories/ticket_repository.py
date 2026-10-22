"""Ticket rows (public.tickets) + the ticket thread (public.replies).

The ticket reference resolver moved here from the old routers/tickets_core:
tickets are addressed as `TKT-<n>` (what the frontend uses in URLs) or by raw
Postgres uuid, and every repo lookup needs the same (column, value) mapping.

Observability: the WRITE paths are instrumented (``ticket.repository.insert_*
``), plus the shared update builder (``ticket.repository.update_*``) and reply
inserts (``reply.repository.*``). They are complementary to run()'s db_span
(trace layer) — safe metadata only: table, patched COLUMN NAMES (never
values), duration, error class, generated refs/uuids. Read paths stay
uninstrumented on purpose: middleware lines + httpx rows cover them, and a
log per read would be pure noise.
"""

import re
import time
from typing import Optional

from app.observability import flow_event
from app.repositories.base import (
    UUID_RE,
    SupabaseRepository,
    first_of,
    rows_of,
)

REF_RE = re.compile(r"^TKT-\d+$")

REF_FIELD = "ref"
ID_FIELD = "id"


def ticket_ref(tid: str) -> tuple[str, str]:
    """Resolve a UUID or a TKT-<n> reference to (column, value)."""
    if UUID_RE.match(tid):
        return ID_FIELD, tid
    col_val = tid if REF_RE.match(tid) else f"TKT-{tid}"
    return REF_FIELD, col_val


class TicketRepository(SupabaseRepository):
    TABLE_NAME = "tickets"

    # -- reads -------------------------------------------------------------

    def get_by_key(self, tid: str) -> Optional[dict]:
        col, val = ticket_ref(tid)
        return first_of(self.table().select("*").eq(col, val).limit(1))

    def list_filtered(
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
        """Newest-first by updated_at; list items never embed the thread."""
        query = self.table().select("*").order("updated_at", desc=True).limit(min(limit, 500))
        if status:
            query = query.eq("status", status)
        if category:
            query = query.eq("category", category)
        if priority:
            query = query.eq("priority", priority)
        if employee_id:
            query = query.eq("employee_id", employee_id)
        if assignee_id:
            query = query.eq("assignee_id", assignee_id)
        if unassigned:
            query = query.is_("assignee_id", None)
        if q:
            query = query.ilike("subject", f"%{q}%")
        return rows_of(query)

    def scan_assignee_status(self, limit: int = 2000) -> list[dict]:
        """Lightweight full scan for workload aggregation in Python (v2 supabase
        has no .not_ chains; one small scan beats a dozen queries)."""
        return rows_of(self.table().select("assignee_id,status").limit(limit))

    def unassigned_by_statuses(self, statuses: tuple) -> list[dict]:
        """Used by the SLA sweep: one query per status, results concatenated
        (same shape the old notifications module produced with db())."""
        out = []
        for status in statuses:
            out.extend(
                rows_of(self.table().select("*").is_("assignee_id", None).eq("status", status))
            )
        return out

    # -- writes ------------------------------------------------------------

    def insert_ticket(self, row: dict, operation: str = "tickets.create") -> dict:
        """POST /tickets + draft-submit write step — instrumented. The
        operation tag identifies the calling flow (create vs drafts.submit)."""
        started = time.perf_counter()
        flow_event(
            "ticket.repository.insert_started",
            operation=operation,
            table="tickets",
        )
        try:
            new_row = rows_of(self.table().insert(row).select("*"))[0]
        except Exception as exc:
            flow_event(
                "ticket.repository.insert_failed",
                operation=operation,
                table="tickets",
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=type(exc).__name__,
            )
            raise
        flow_event(
            "ticket.repository.insert_completed",
            operation=operation,
            table="tickets",
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            ticket_ref=new_row.get("ref"),
            status=new_row.get("status"),
        )
        return new_row

    def update_ticket(self, ticket_uuid: str, patch: dict) -> None:
        """Patch by uuid (the trigger bumps updated_at). Instrumented: which
        COLUMNS changed (never their values) + duration."""
        started = time.perf_counter()
        patch_columns = sorted(patch)
        flow_event(
            "ticket.repository.update_started",
            operation=None,  # several flows share this builder
            table="tickets",
            patch_columns=patch_columns,
        )
        try:
            rows_of(self.table().update(patch).eq("id", ticket_uuid))
        except Exception as exc:
            flow_event(
                "ticket.repository.update_failed",
                table="tickets",
                patch_columns=patch_columns,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=type(exc).__name__,
            )
            raise
        flow_event(
            "ticket.repository.update_completed",
            table="tickets",
            patch_columns=patch_columns,
            ticket_uuid=ticket_uuid,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )

    # -- replies / thread --------------------------------------------------

    def list_replies(self, ticket_uuid: str) -> list[dict]:
        return rows_of(
            self._client.table("replies")
            .select("*")
            .eq("ticket_id", ticket_uuid)
            .order("created_at")
        )

    def insert_reply(self, row: dict, operation: str | None = None) -> dict:
        inserted: dict = {}
        started = time.perf_counter()
        flow_event(
            "reply.repository.insert_started",
            operation=operation,
            author_role=row.get("author_role"),
        )
        try:
            inserted = rows_of(
                self._client.table("replies").insert(row).select("*")
            )[0]
        except Exception as exc:
            flow_event(
                "reply.repository.insert_failed",
                operation=operation,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                error=type(exc).__name__,
            )
            raise
        flow_event(
            "reply.repository.insert_completed",
            operation=operation,
            reply_uuid=inserted.get("id"),
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return inserted

    def has_agent_reply(self, ticket_uuid: str) -> bool:
        return bool(
            rows_of(
                self._client.table("replies")
                .select("id")
                .eq("ticket_id", ticket_uuid)
                .eq("author_role", "agent")
                .limit(1)
            )
        )
