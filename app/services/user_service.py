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
        """Employees first, then agents, then admins (each group
        newest-account-last).

        Admins MUST be included: after sign-in the frontend re-checks the
        signed-in account against this directory and drops the session when
        the id is missing — an admin absent from the list would be signed
        out automatically right after a successful login.
        """
        ordered = (
            self._users.list_by_role("employee")
            + self._users.list_by_role("agent")
            + self._users.list_by_role("admin")
        )
        return [user_out(u) for u in ordered]

    def list_agents(self) -> list[dict]:
        return [user_out(u) for u in self._users.agents()]

    @staticmethod
    def meta() -> dict:
        """Categories/priorities/statuses — one payload, frontend defaults."""
        return {"categories": CATEGORIES, "priorities": PRIORITIES, "statuses": STATUSES}
