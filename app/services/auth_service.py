"""Database-backed authentication for organisation-managed HR Desk accounts."""

import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app import config
from app.models import user_out
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.user_repository import UserRepository
from app.services.mailpit import send_password_reset_otp
from app.services.passwords import hash_password, verify_password
from app.services.tokens import create_access_token


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
    def __init__(self, users: UserRepository, resets: PasswordResetRepository | None = None):
        self._users = users
        self._resets = resets

    def login(self, email: str, password: str) -> dict:
        """Verify credentials, upgrade legacy hashes, and issue a bearer token."""
        email = clean_email(email)
        row = self._users.get_credentials_by_email(email)
        password_hash = row.get("password_hash") if row else None
        if not verify_password(password, password_hash or _DUMMY_PASSWORD_HASH) or not row:
            raise HTTPException(status_code=401, detail="Invalid email or password.")
        if password_hash and password_hash.startswith("scrypt$"):
            if len(password.encode("utf-8")) <= 72:
                if not self._users.upgrade_password_hash(
                    row["id"], password_hash, hash_password(password)
                ):
                    raise HTTPException(status_code=401, detail="Invalid email or password.")
            row = self._users.get_credentials_by_email(email)
        return {
            "user": user_out(row),
            "accessToken": create_access_token(row),
            "tokenType": "bearer",
            "expiresIn": config.AUTH_TOKEN_TTL_SECONDS,
        }

    def change_password(self, user: dict, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.get("password_hash") or ""):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        if current_password == new_password:
            raise HTTPException(
                status_code=422,
                detail="New password must be different from the current password.",
            )
        self._users.set_password_hash(user["id"], _validated_password_hash(new_password))

    def request_password_reset(self, email: str) -> None:
        if not self._resets:
            raise RuntimeError("Password reset repository is not configured.")
        cleaned_email = clean_email(email)
        user = self._users.get_credentials_by_email(cleaned_email)
        if not user:
            return
        existing = self._resets.get_for_email(cleaned_email)
        if existing:
            requested_at = existing["created_at"]
            if isinstance(requested_at, str):
                requested_at = datetime.fromisoformat(requested_at.replace("Z", "+00:00"))
            if requested_at.tzinfo is None:
                requested_at = requested_at.replace(tzinfo=timezone.utc)
            if requested_at + timedelta(seconds=60) > datetime.now(timezone.utc):
                return
        otp = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=config.PASSWORD_RESET_OTP_TTL_SECONDS
        )
        otp_hash = hash_password(otp)
        self._resets.replace_otp(user["id"], otp_hash, expires_at)
        try:
            send_password_reset_otp(cleaned_email, otp)
        except HTTPException:
            self._resets.remove_otp(user["id"], otp_hash)
            raise

    def reset_password(self, email: str, otp: str, new_password: str) -> None:
        if not self._resets:
            raise RuntimeError("Password reset repository is not configured.")
        cleaned_email = clean_email(email)
        challenge = self._resets.get_for_email(cleaned_email)
        if not challenge or challenge["attempts"] >= 5:
            raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
        expiry = challenge["expires_at"]
        if isinstance(expiry, str):
            expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
        if not verify_password(otp, challenge["otp_hash"]):
            self._resets.increment_attempts(challenge["user_id"])
            raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
        password_hash = _validated_password_hash(new_password)
        if not self._resets.consume_otp(challenge["user_id"]):
            raise HTTPException(status_code=400, detail="Invalid or expired reset code.")
        self._users.set_password_hash(challenge["user_id"], password_hash)


def _validated_password_hash(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=422, detail="Password must be at most 72 UTF-8 bytes.")
    return hash_password(password)


__all__ = ["AuthService", "clean_email", "hash_password", "verify_password"]
