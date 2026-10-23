"""PostgreSQL ticket rows and ticket-thread operations."""

import re
import time
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
        filters = []
        params = []
        for column, value in (
            ("status", status),
            ("category", category),
            ("priority", priority),
            ("employee_id", employee_id),
            ("assignee_id", assignee_id),
        ):
            if value is not None:
                filters.append(f"{column} = %s")
                params.append(as_uuid(value) if column in ("employee_id", "assignee_id") else value)
        if unassigned:
            filters.append("assignee_id IS NULL")
        if q:
            filters.append("subject ILIKE %s")
            params.append(f"%{q}%")
        where = f" WHERE {' AND '.join(filters)}" if filters else ""
        params.append(min(limit, 500))
        return rows_of(
            self._database,
            f"SELECT * FROM tickets{where} ORDER BY updated_at DESC LIMIT %s",
            tuple(params),
            table="tickets",
        )

    def scan_assignee_status(self, limit: int = 2000) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT assignee_id, status FROM tickets LIMIT %s",
            (limit,),
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
