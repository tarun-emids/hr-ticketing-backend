"""PostgreSQL ticket rows and ticket-thread operations."""

import re
import time
import uuid
from contextlib import contextmanager
from typing import Optional

from psycopg_pool import ConnectionPool

from app.observability import flow_event
from app.repositories.base import UUID_RE, as_uuid, first_of, insert_row, rows_of, update_row

REF_RE = re.compile(r"^TKT-\d+$")


@contextmanager
def _repository_operation(event: str, operation: str, **fields):
    started = time.perf_counter()
    flow_event(f"{event}_started", operation=operation, **fields)
    extras = {}
    try:
        yield extras
    except Exception as error:
        status = getattr(error, "status_code", None)
        flow_event(
            f"{event}_failed",
            operation=operation,
            status=status if isinstance(status, int) else None,
            error=type(error).__name__,
            **fields,
            **extras,
        )
        raise
    flow_event(
        f"{event}_completed",
        operation=operation,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
        **fields,
        **extras,
    )


def ticket_ref(tid: str) -> tuple[str, str]:
    """Resolve a UUID or a TKT-<n> reference to (column, value)."""
    if UUID_RE.match(tid):
        return "id", tid
    return "ref", tid if REF_RE.match(tid) else f"TKT-{tid}"


# Whitelisted sort options. Values are fixed SQL expressions; the client
# string only ever *selects* one of these — it is never interpolated.
_SORT_EXPRESSIONS = {
    "updated": "updated_at",
    "created": "created_at",
    "priority": (
        "CASE priority WHEN 'Urgent' THEN 4 WHEN 'High' THEN 3 WHEN 'Medium' THEN 2 ELSE 1 END"
    ),
    "subject": "LOWER(subject)",
    "status": (
        "CASE status WHEN 'Open' THEN 1 WHEN 'In Progress' THEN 2"
        " WHEN 'Waiting on Employee' THEN 3 WHEN 'Resolved' THEN 4 ELSE 5 END"
    ),
    "employee": "LOWER(users.name)",
}
_SORT_DIRECTIONS = {"asc": "ASC", "desc": "DESC"}


class TicketRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def get_by_key(self, tid: str) -> Optional[dict]:
        column, value = ticket_ref(tid)
        return first_of(
            self._database,
            f"SELECT * FROM tickets WHERE {column} = %s LIMIT 1",
            (as_uuid(value) if column == "id" else value,),
            table="tickets",
        )

    def _ticket_filters(
        self,
        *,
        employee_scope_id: Optional[uuid.UUID],
        status: Optional[str],
        category: Optional[str],
        priority: Optional[str],
        employee_id: Optional[str],
        assignee_id: Optional[str],
        q: Optional[str],
        unassigned: bool,
    ) -> tuple[list[str], list]:
        """Single source of truth for ticket-list/scope predicates: the WHERE
        fragments and their parameter values. Both the page query and the
        total-count query build on them, so the two can never disagree about
        what a filtered view contains. Returns fresh lists; callers append
        statement-specific parameters (LIMIT) only to their own copies."""
        filters: list[str] = []
        params: list = []
        if employee_scope_id is not None:
            filters.append("employee_id = %s")
            params.append(employee_scope_id)
        for column, value in (("status", status), ("category", category), ("priority", priority)):
            if value is not None:
                filters.append(f"{column} = %s")
                params.append(value)
        for column, value in (("employee_id", employee_id), ("assignee_id", assignee_id)):
            if value is not None:
                filters.append(f"{column} = %s")
                params.append(as_uuid(value))
        if unassigned:
            filters.append("assignee_id IS NULL")
        if q:
            filters.append("subject ILIKE %s")
            params.append(f"%{q}%")
        return filters, params

    def list_filtered(
        self,
        *,
        employee_scope_id: Optional[uuid.UUID] = None,
        sort: str = "updated",
        order: str = "desc",
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        employee_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        q: Optional[str] = None,
        unassigned: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict]:
        filters, params = self._ticket_filters(
            employee_scope_id=employee_scope_id,
            status=status,
            category=category,
            priority=priority,
            employee_id=employee_id,
            assignee_id=assignee_id,
            q=q,
            unassigned=unassigned,
        )
        from_clause = "tickets"
        if sort == "employee":
            from_clause = "tickets LEFT JOIN users ON users.id = tickets.employee_id"
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        params = [*params, min(limit, 500), offset]
        return rows_of(
            self._database,
            f"SELECT tickets.* FROM {from_clause}{where}"
            f" ORDER BY {_SORT_EXPRESSIONS[sort]} {_SORT_DIRECTIONS[order]},"
            f" updated_at DESC, number DESC LIMIT %s OFFSET %s",
            tuple(params),
            table="tickets",
        )

    def count_filtered(
        self,
        *,
        employee_scope_id: Optional[uuid.UUID] = None,
        status: Optional[str] = None,
        category: Optional[str] = None,
        priority: Optional[str] = None,
        employee_id: Optional[str] = None,
        assignee_id: Optional[str] = None,
        q: Optional[str] = None,
        unassigned: bool = False,
    ) -> int:
        """Exact total for one filtered ticket view — the aggregate count over
        the IDENTICAL predicate list_filtered uses, no LIMIT attached."""
        filters, params = self._ticket_filters(
            employee_scope_id=employee_scope_id,
            status=status,
            category=category,
            priority=priority,
            employee_id=employee_id,
            assignee_id=assignee_id,
            q=q,
            unassigned=unassigned,
        )
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        row = first_of(
            self._database,
            f"SELECT count(*) AS total FROM tickets{where}",
            tuple(params),
            table="tickets",
        )
        return int(row["total"])

    def scan_assignee_status(self, limit: int = 2000) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT assignee_id, status FROM tickets LIMIT %s",
            (limit,),
            table="tickets",
        )

    def count_by_assignee(self, statuses: tuple[str, ...]) -> list[dict]:
        """Per-assignee workload counters: one row per assignee with its
        total and the count within `statuses`. Unassigned tickets form no
        group; agents without tickets are absent here — the service
        supplies [0, 0] defaults. No LIMIT: the aggregation runs entirely
        in the database, so no row ceiling exists to outlive."""
        placeholders = ", ".join(["%s"] * len(statuses))
        return rows_of(
            self._database,
            f"SELECT assignee_id AS agent_id, count(*) AS total_count,"
            f" sum(CASE WHEN status IN ({placeholders}) THEN 1 ELSE 0 END) AS open_count"
            f" FROM tickets WHERE assignee_id IS NOT NULL GROUP BY assignee_id",
            tuple(statuses),
            table="tickets",
        )

    def unassigned_by_statuses(self, statuses: tuple) -> list[dict]:
        placeholders = ", ".join(["%s"] * len(statuses))
        return rows_of(
            self._database,
            f"SELECT * FROM tickets WHERE assignee_id IS NULL AND status IN ({placeholders})",
            statuses,
            table="tickets",
        )

    def insert_ticket(self, row: dict, *, operation: Optional[str] = None) -> dict:
        if operation is None:
            return insert_row(self._database, "tickets", row)
        with _repository_operation(
            "ticket.repository.insert", operation=operation, table="tickets"
        ) as event:
            result = insert_row(self._database, "tickets", row)
            event["ticket_ref"] = result.get("ref")
            return result

    def update_ticket(
        self, ticket_uuid: str, patch: dict, *, operation: Optional[str] = None
    ) -> None:
        if operation is None:
            update_row(self._database, "tickets", ticket_uuid, patch)
            return
        with _repository_operation(
            "ticket.repository.update",
            operation=operation,
            table="tickets",
            patch_columns=sorted(patch),
        ):
            update_row(self._database, "tickets", ticket_uuid, patch)

    def list_replies(self, ticket_uuid: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT * FROM replies WHERE ticket_id = %s ORDER BY created_at",
            (as_uuid(ticket_uuid),),
            table="replies",
        )

    def insert_reply(self, row: dict, *, operation: Optional[str] = None) -> dict:
        if operation is None:
            return insert_row(self._database, "replies", row)
        with _repository_operation(
            "reply.repository.insert",
            operation=operation,
            table="replies",
            author_role=row.get("author_role"),
        ):
            return insert_row(self._database, "replies", row)

    def has_agent_reply(self, ticket_uuid: str) -> bool:
        return bool(
            first_of(
                self._database,
                "SELECT id FROM replies WHERE ticket_id = %s AND author_role = %s LIMIT 1",
                (as_uuid(ticket_uuid), "agent"),
                table="replies",
            )
        )
