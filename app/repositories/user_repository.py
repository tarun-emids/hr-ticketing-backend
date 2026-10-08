"""User rows (public.users): employees + HR agents."""
from typing import Optional

from app.repositories.base import SupabaseRepository, first_of, rows_of


class UserRepository(SupabaseRepository):
    TABLE_NAME = "users"

    def get_by_id(self, user_id: str) -> Optional[dict]:
        if not user_id:
            return None
        return first_of(self.table().select("*").eq("id", user_id).limit(1))

    def get_by_email_case_insensitive(self, email: str) -> Optional[dict]:
        """Case-insensitive lookup used by the auth service.

        GoTrue stores emails lowercased, but rows in public.users may have
        been entered with different casing. Caller must pre-escape LIKE
        wildcards (see services/auth_service._like_safe).
        """
        return first_of(
            self.table().select("*").ilike("email", email).limit(1)
        )

    def list_by_role(self, role: str) -> list[dict]:
        """Ordered by account creation date (stable demo ordering)."""
        return rows_of(
            self.table().select("*").eq("role", role).order("created_at")
        )

    def agents(self) -> list[dict]:
        return self.list_by_role("agent")

    def agent_ids(self) -> list:
        return [r["id"] for r in rows_of(self.table().select("id").eq("role", "agent"))]
