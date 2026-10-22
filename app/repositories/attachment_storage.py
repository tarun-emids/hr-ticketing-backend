"""PostgreSQL-backed attachment blobs and short-lived signed download URLs."""

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException
from psycopg_pool import ConnectionPool

from app import config
from app.config import MAX_ATTACHMENT_BYTES, SIGNED_URL_TTL
from app.repositories.base import first_of, run

MB = 1024 * 1024
DOWNLOAD_PATH = "/api/attachments/file"


class AttachmentStorageRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    @staticmethod
    def clamp_ttl(ttl: int) -> int:
        return max(60, min(ttl, 86400))

    @staticmethod
    def _signing_key() -> bytes:
        key = config.ATTACHMENT_SIGNING_KEY.encode()
        if len(key) < 32:
            raise RuntimeError("ATTACHMENT_SIGNING_KEY must contain at least 32 characters.")
        return key

    def upload(self, path: str, data: bytes, content_type: str | None) -> None:
        run(
            self._database,
            "INSERT INTO attachments (path, data, content_type) VALUES (%s, %s, %s)",
            (path, data, content_type or "application/octet-stream"),
            fetch="none",
            table="attachments",
        )

    def remove(self, path: str) -> None:
        run(
            self._database,
            "DELETE FROM attachments WHERE path = %s",
            (path,),
            fetch="none",
            table="attachments",
        )

    def signed_url(self, path: str, ttl: int = SIGNED_URL_TTL) -> str:
        expires = int(time.time()) + self.clamp_ttl(ttl)
        encoded_path = base64.urlsafe_b64encode(path.encode()).decode().rstrip("=")
        payload = f"{encoded_path}.{expires}"
        signature = hmac.new(self._signing_key(), payload.encode(), hashlib.sha256).hexdigest()
        return f"{DOWNLOAD_PATH}/{payload}.{signature}"

    def read_signed(self, token: str) -> tuple[bytes, str]:
        try:
            encoded_path, raw_expires, signature = token.split(".", 2)
            expires = int(raw_expires)
            payload = f"{encoded_path}.{expires}"
            expected = hmac.new(self._signing_key(), payload.encode(), hashlib.sha256).hexdigest()
            if expires < int(time.time()) or not hmac.compare_digest(signature, expected):
                raise ValueError
            padded_path = encoded_path + "=" * (-len(encoded_path) % 4)
            path = base64.urlsafe_b64decode(padded_path.encode()).decode()
        except ValueError, UnicodeDecodeError:
            raise HTTPException(
                status_code=404, detail="Attachment link is invalid or expired."
            ) from None

        row = first_of(
            self._database,
            "SELECT data, content_type FROM attachments WHERE path = %s",
            (path,),
            table="attachments",
        )
        if not row:
            raise HTTPException(status_code=404, detail="Attachment not found.")
        return row["data"], row["content_type"]

    @staticmethod
    def check_size(data: bytes) -> None:
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is larger than {MAX_ATTACHMENT_BYTES // MB} MB",
            )
