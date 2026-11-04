"""Database-backed authentication for organisation-managed HR Desk accounts."""

import re
import secrets
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from fastapi import HTTPException

from app import config
from app.models import user_out
from app.repositories.user_repository import UserRepository
from app.services.passwords import hash_password, verify_password

PASSWORD_RESET_TTL = timedelta(minutes=10)
PASSWORD_RESET_MESSAGE = "If an account exists for this address, a reset code has been emailed."


def _invisible_chars_pattern() -> str:
    ranges = [
        (0x200B, 0x200F),
        (0x2028, 0x202F),
        (0x2060, 0x2064),
        (0x2066, 0x206F),
        (0x00AD, 0x00AD),
        (0xFEFF, 0xFEFF),
        (0x00A0, 0x00A0),
        (0x1680, 0x1680),
        (0x2000, 0x200A),
        (0x205F, 0x205F),
        (0x3000, 0x3000),
    ]
    parts = []
    for low, high in ranges:
        first, last = re.escape(chr(low)), re.escape(chr(high))
        parts.append(first if low == high else f"{first}-{last}")
    return "[" + "".join(parts) + "]"


_INVISIBLE_CHARS = re.compile(_invisible_chars_pattern())


def clean_email(raw: str) -> str:
    return _INVISIBLE_CHARS.sub("", raw.strip()).lower()


def send_password_reset_email(recipient: str, code: str) -> None:
    message = EmailMessage()
    message["Subject"] = "Your HR Desk password reset code"
    message["From"] = config.SMTP_FROM
    message["To"] = recipient
    message.set_content(
        f"Your HR Desk password reset code is {code}. "
        "It expires in 10 minutes. If you did not request this, you can ignore this email."
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as smtp:
        if config.SMTP_STARTTLS:
            smtp.starttls()
        if config.SMTP_USERNAME:
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        smtp.send_message(message)


_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


class AuthService:
    def __init__(self, users: UserRepository, reset_email_sender=None):
        self._users = users
        self._reset_email_sender = reset_email_sender

    def login(self, email: str, password: str) -> dict:
        """Verify the stored scrypt hash and return the public user record."""
        email = clean_email(email)
        row = self._users.get_credentials_by_email(email)
        password_hash = row.get("password_hash") if row else None
        if not verify_password(password, password_hash or _DUMMY_PASSWORD_HASH) or not row:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        return {"user": user_out(row)}

    def request_password_reset(self, email: str) -> dict:
        email = clean_email(email)
        user = self._users.get_password_reset_account_by_email(email)
        if not user:
            return {"message": PASSWORD_RESET_MESSAGE}

        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = hash_password(code)
        now = datetime.now(timezone.utc)
        self._users.store_password_reset_code(user["id"], code_hash, now + PASSWORD_RESET_TTL)
        try:
            sender = self._reset_email_sender or send_password_reset_email
            sender(user["email"], code)
        except (OSError, smtplib.SMTPException) as exc:
            self._users.delete_password_reset_code(user["id"], code_hash)
            raise HTTPException(
                status_code=503,
                detail="Password reset email is temporarily unavailable. Please try again.",
            ) from exc
        return {"message": PASSWORD_RESET_MESSAGE}

    def reset_password(self, email: str, code: str, new_password: str) -> dict:
        email = clean_email(email)
        if len(new_password.encode("utf-8")) > 72:
            raise HTTPException(
                status_code=422,
                detail="Your password must be at most 72 UTF-8 bytes.",
            )

        user = self._users.get_password_reset_account_by_email(email)
        reset = self._users.get_password_reset_code(user["id"]) if user else None
        if not reset or not verify_password(code, reset["code_hash"]):
            raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

        now = datetime.now(timezone.utc)
        expires_at = reset["expires_at"]
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now or not self._users.consume_password_reset_code(
            user["id"], reset["code_hash"], now
        ):
            raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

        self._users.set_password_hash(user["id"], hash_password(new_password))
        return {"message": "Password reset successfully. Please sign in with your new password."}


__all__ = ["AuthService", "clean_email", "hash_password", "verify_password"]
