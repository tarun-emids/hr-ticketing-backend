"""Database-backed authentication for organisation-managed HR Desk accounts."""

import re

from fastapi import HTTPException

from app.models import user_out
from app.repositories.user_repository import UserRepository
from app.services.passwords import hash_password, verify_password


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


_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


class AuthService:
    def __init__(self, users: UserRepository):
        self._users = users

    def login(self, email: str, password: str) -> dict:
        """Verify the stored scrypt hash and return the public user record."""
        email = clean_email(email)
        row = self._users.get_credentials_by_email(email)
        password_hash = row.get("password_hash") if row else None
        if not verify_password(password, password_hash or _DUMMY_PASSWORD_HASH) or not row:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        return {"user": user_out(row)}


__all__ = ["AuthService", "clean_email", "hash_password", "verify_password"]
