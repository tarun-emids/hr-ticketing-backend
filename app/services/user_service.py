"""User / directory service: lists and static meta values (replaces the old
src/data/users.js mocks). Serialization happens here (user_out), controllers
return the lists untouched.
"""

from app.models import CATEGORIES, PRIORITIES, STATUSES, user_out
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, users: UserRepository):
        self._users = users

    def list_users(self) -> list[dict]:
        """Employees first, then agents (each group newest-account-last)."""
        ordered = self._users.list_by_role("employee") + self._users.list_by_role("agent")
        return [user_out(u) for u in ordered]

    def list_agents(self) -> list[dict]:
        return [user_out(u) for u in self._users.agents()]

    @staticmethod
    def meta() -> dict:
        """Categories/priorities/statuses — one payload, frontend defaults."""
        return {"categories": CATEGORIES, "priorities": PRIORITIES, "statuses": STATUSES}
