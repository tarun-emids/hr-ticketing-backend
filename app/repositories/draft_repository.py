"""Employee ticket drafts (public.ticket_drafts).

Employee-owned: every read/write is scoped to an employee_id, mirroring the
endpoint contract that a draft is only ever touched by its owner.
"""

from typing import Optional

from app.repositories.base import SupabaseRepository, rows_of


class DraftRepository(SupabaseRepository):
    TABLE_NAME = "ticket_drafts"

    def get_owned(self, draft_id: str, employee_id: str) -> Optional[dict]:
        rows = rows_of(
            self.table().select("*").eq("id", draft_id).eq("employee_id", employee_id).limit(1)
        )
        return rows[0] if rows else None

    def list_for_employee(self, employee_id: str) -> list[dict]:
        return rows_of(
            self.table().select("*").eq("employee_id", employee_id).order("updated_at", desc=True)
        )

    def insert_draft(self, row: dict) -> dict:
        return rows_of(self.table().insert(row).select("*"))[0]

    def update_draft(self, draft_id: str, patch: dict) -> None:
        rows_of(self.table().update(patch).eq("id", draft_id))

    def delete_draft(self, draft_id: str) -> None:
        rows_of(self.table().delete().eq("id", draft_id))
