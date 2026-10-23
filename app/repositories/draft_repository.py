"""PostgreSQL access for employee-owned ticket drafts."""

from typing import Optional

from psycopg_pool import ConnectionPool

from app.repositories.base import UUID_RE, as_uuid, first_of, insert_row, rows_of, run, update_row


class DraftRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def get_owned(self, draft_id: str, employee_id: str) -> Optional[dict]:
        if not UUID_RE.fullmatch(draft_id) or not UUID_RE.fullmatch(employee_id):
            return None
        return first_of(
            self._database,
            "SELECT * FROM ticket_drafts WHERE id = %s AND employee_id = %s LIMIT 1",
            (as_uuid(draft_id), as_uuid(employee_id)),
            table="ticket_drafts",
        )

    def list_for_employee(self, employee_id: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT * FROM ticket_drafts WHERE employee_id = %s ORDER BY updated_at DESC",
            (as_uuid(employee_id),),
            table="ticket_drafts",
        )

    def insert_draft(self, row: dict) -> dict:
        return insert_row(self._database, "ticket_drafts", row)

    def update_draft(self, draft_id: str, patch: dict) -> None:
        update_row(self._database, "ticket_drafts", draft_id, patch)

    def delete_draft(self, draft_id: str) -> None:
        run(
            self._database,
            "DELETE FROM ticket_drafts WHERE id = %s",
            (as_uuid(draft_id),),
            fetch="none",
            table="ticket_drafts",
        )
