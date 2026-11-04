"""Persistence for short-lived password-reset OTP challenges."""

from datetime import datetime

from psycopg_pool import ConnectionPool

from app.repositories.base import first_of, run


class PasswordResetRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def replace_otp(self, user_id: str, otp_hash: str, expires_at: datetime) -> None:
        run(
            self._database,
            "INSERT INTO password_reset_otps (user_id, otp_hash, expires_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET "
            "otp_hash = EXCLUDED.otp_hash, expires_at = EXCLUDED.expires_at, "
            "attempts = 0, created_at = CURRENT_TIMESTAMP",
            (user_id, otp_hash, expires_at),
            fetch="none",
            table="password_reset_otps",
        )

    def get_for_email(self, email: str) -> dict | None:
        return first_of(
            self._database,
            "SELECT r.user_id, r.otp_hash, r.expires_at, r.attempts, r.created_at "
            "FROM password_reset_otps r JOIN users u ON u.id = r.user_id "
            "WHERE lower(u.email) = lower(%s)",
            (email,),
            table="password_reset_otps",
        )

    def increment_attempts(self, user_id: str) -> int:
        return run(
            self._database,
            "UPDATE password_reset_otps SET attempts = attempts + 1 "
            "WHERE user_id = %s AND attempts < 5",
            (user_id,),
            fetch="none",
            table="password_reset_otps",
        )

    def remove_otp(self, user_id: str, otp_hash: str) -> int:
        return run(
            self._database,
            "DELETE FROM password_reset_otps WHERE user_id = %s AND otp_hash = %s",
            (user_id, otp_hash),
            fetch="none",
            table="password_reset_otps",
        )

    def consume_otp(self, user_id: str) -> int:
        return run(
            self._database,
            "DELETE FROM password_reset_otps WHERE user_id = %s AND attempts < 5",
            (user_id,),
            fetch="none",
            table="password_reset_otps",
        )
