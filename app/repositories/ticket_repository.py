"""PostgreSQL ticket rows and ticket-thread operations."""

import re
from typing import Optional

from psycopg_pool import ConnectionPool

from app.repositories.base import UUID_RE, as_uuid, first_of, insert_row, rows_of, update_row

REF_RE = re.compile(r"^TKT-\d+$")


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

    def insert_ticket(self, row: dict) -> dict:
        return insert_row(self._database, "tickets", row)

    def update_ticket(self, ticket_uuid: str, patch: dict) -> None:
        update_row(self._database, "tickets", ticket_uuid, patch)

    def list_replies(self, ticket_uuid: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT * FROM replies WHERE ticket_id = %s ORDER BY created_at",
            (as_uuid(ticket_uuid),),
            table="replies",
        )

    def insert_reply(self, row: dict) -> dict:
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
