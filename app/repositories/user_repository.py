"""PostgreSQL access for employee and HR-agent accounts."""

from typing import Optional
from uuid import UUID

from psycopg_pool import ConnectionPool

from app.repositories.base import UUID_RE, as_uuid, first_of, rows_of, run


class UserRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def get_by_id(self, user_id: str | UUID) -> Optional[dict]:
        if not user_id or (isinstance(user_id, str) and not UUID_RE.fullmatch(user_id)):
            return None
        return first_of(
            self._database,
            "SELECT * FROM users WHERE id = %s LIMIT 1",
            (as_uuid(user_id),),
            table="users",
        )

    def get_by_email_case_insensitive(self, email: str) -> Optional[dict]:
        return first_of(
            self._database,
            "SELECT * FROM users WHERE lower(email) = lower(%s) LIMIT 1",
            (email,),
            table="users",
        )

    def get_credentials_by_email(self, email: str) -> Optional[dict]:
        return first_of(
            self._database,
            "SELECT id, name, email, role, password_hash FROM users "
            "WHERE lower(email) = lower(%s) LIMIT 1",
            (email,),
            table="users",
        )

    def accounts(self) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT id, name, email, role FROM users ORDER BY created_at",
            table="users",
        )

    def set_password_hash(self, user_id: str, password_hash: str) -> None:
        run(
            self._database,
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (password_hash, as_uuid(user_id)),
            fetch="none",
            table="users",
        )

    def list_by_role(self, role: str) -> list[dict]:
        return rows_of(
            self._database,
            "SELECT * FROM users WHERE role = %s ORDER BY created_at",
            (role,),
            table="users",
        )

    def agents(self) -> list[dict]:
        return self.list_by_role("agent")

    def agent_ids(self) -> list:
        rows = rows_of(
            self._database,
            "SELECT id FROM users WHERE role = %s",
            ("agent",),
            table="users",
        )
        return [row["id"] for row in rows]
