"""Account administration: create, re-role (promote/demote), delete.

Safety rules (all server-enforced, all surfaced as 409 so the console
can print them verbatim):

1. DEMOTE never orphans a workspace: an agent with open assigned tickets
   must have them reassigned or resolved first.
2. DELETE never destroys history: accounts that authored replies or are
   referenced by tickets (employee of or assignee on) cannot be deleted —
   that data models a real person's work.
3. The LAST admin cannot be demoted or deleted (or the console bricks).
4. Email uniqueness is case-insensitive, matching the login flow.
"""

from fastapi import HTTPException

from app.admin.repository import AdminRepository
from app.models import user_out
from app.repositories.user_repository import UserRepository
from app.services.auth_service import clean_email
from app.services.passwords import hash_password

ROLES = ("employee", "agent", "admin")


def _assert_role(role: str) -> str:
    if role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of: {', '.join(ROLES)}")
    return role


class AdminAccountService:
    def __init__(self, repo: AdminRepository, users: UserRepository):
        self._repo = repo
        self._users = users

    # -- read ------------------------------------------------------------------

    def list_accounts(self) -> list[dict]:
        return [user_out(row) for row in self._users.accounts()]

    # -- create ------------------------------------------------------------------

    def create(self, name: str, email: str, role: str, password: str) -> dict:
        role = _assert_role(role)
        email = clean_email(email)
        if "@" not in email or len(name.strip()) < 2:
            raise HTTPException(status_code=422, detail="Name and a valid email are required.")
        if len(password) < 8:
            raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
        if self._users.get_by_email_case_insensitive(email):
            raise HTTPException(
                status_code=409, detail="An account with that email already exists."
            )
        row = self._repo.insert_account({"name": name.strip(), "email": email, "role": role})
        self._users.set_password_hash(row["id"], hash_password(password))
        return user_out(row)

    # -- re-role (the promotion toggle) --------------------------------------------

    def set_role(self, account_id: str, role: str) -> dict:
        role = _assert_role(role)
        account = self._users.get_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Unknown account")
        current = account.get("role")
        if current == role:
            return user_out(account)
        # demoting an agent with open work orphans it — explicit refusal
        if current in ("agent", "admin") and role == "employee":
            open_tickets = self._repo.open_assigned_count(account_id)
            if open_tickets:
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent still owns {open_tickets} open ticket(s) — reassign or resolve them first.",
                )
        # demoting the last admin would brick the console
        if current == "admin" and role != "admin" and self._repo.admin_count() <= 1:
            raise HTTPException(status_code=409, detail="That is the only admin account.")
        return user_out(self._repo.set_role(account_id, role))

    # -- delete ----------------------------------------------------------------

    def delete(self, account_id: str) -> dict:
        account = self._users.get_by_id(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Unknown account")
        if account.get("role") == "admin" and self._repo.admin_count() <= 1:
            raise HTTPException(status_code=409, detail="That is the only admin account.")
        if self._repo.ticket_references_count(account_id):
            raise HTTPException(
                status_code=409,
                detail="This account is referenced by tickets — delete never destroys ticket history.",
            )
        if self._repo.reply_author_count(account_id):
            raise HTTPException(
                status_code=409,
                detail="This account authored ticket replies — delete never destroys thread history.",
            )
        self._repo.delete_account(account_id)
        return user_out(account)
