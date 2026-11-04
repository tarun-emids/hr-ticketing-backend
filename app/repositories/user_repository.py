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
            "SELECT id, name, email, role, password_hash, auth_version FROM users "
            "WHERE lower(email) = lower(%s) LIMIT 1",
            (email,),
            table="users",
        )

    def get_password_reset_account_by_email(self, email: str) -> Optional[dict]:
        return first_of(
            self._database,
            "SELECT id, name, email FROM users WHERE lower(email) = lower(%s) LIMIT 1",
            (email,),
            table="users",
        )

    def get_password_reset_code(self, user_id: str) -> Optional[dict]:
        return first_of(
            self._database,
            "SELECT code_hash, expires_at FROM password_reset_codes WHERE user_id = %s",
            (as_uuid(user_id),),
            table="password_reset_codes",
        )

    def store_password_reset_code(self, user_id: str, code_hash: str, expires_at) -> None:
        run(
            self._database,
            "INSERT INTO password_reset_codes (user_id, code_hash, expires_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
            "code_hash = EXCLUDED.code_hash, expires_at = EXCLUDED.expires_at, "
            "created_at = CURRENT_TIMESTAMP",
            (as_uuid(user_id), code_hash, expires_at),
            fetch="none",
            table="password_reset_codes",
        )

    def consume_password_reset_code(self, user_id: str, code_hash: str, now) -> bool:
        return bool(
            run(
                self._database,
                "DELETE FROM password_reset_codes "
                "WHERE user_id = %s AND code_hash = %s AND expires_at > %s",
                (as_uuid(user_id), code_hash, now),
                fetch="none",
                table="password_reset_codes",
            )
        )

    def delete_password_reset_code(self, user_id: str, code_hash: str) -> None:
        run(
            self._database,
            "DELETE FROM password_reset_codes WHERE user_id = %s AND code_hash = %s",
            (as_uuid(user_id), code_hash),
            fetch="none",
            table="password_reset_codes",
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
            "UPDATE users SET password_hash = %s, auth_version = auth_version + 1 WHERE id = %s",
            (password_hash, as_uuid(user_id)),
            fetch="none",
            table="users",
        )

    def upgrade_password_hash(self, user_id: str, old_hash: str, new_hash: str) -> int:
        return run(
            self._database,
            "UPDATE users SET password_hash = %s, auth_version = auth_version + 1 "
            "WHERE id = %s AND password_hash = %s",
            (new_hash, as_uuid(user_id), old_hash),
            fetch="none",
            table="users",
    def set_password_hash_if_missing(self, user_id: str, password_hash: str) -> bool:
        return bool(
            run(
                self._database,
                "UPDATE users SET password_hash = %s "
                "WHERE id = %s AND password_hash IS NULL",
                (password_hash, as_uuid(user_id)),
                fetch="none",
                table="users",
            )
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
