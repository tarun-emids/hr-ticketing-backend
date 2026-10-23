"""PostgreSQL-backed knowledge-base PDFs with short-lived signed links."""

import hashlib
import hmac
import re
import time
from typing import Optional
from urllib.parse import urlencode

from fastapi import HTTPException
from psycopg_pool import ConnectionPool

from app import config
from app.config import SIGNED_URL_TTL
from app.repositories.base import first_of

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')
_PDF_PATH = "/api/kb/pdf"


def safe_download_name(title: Optional[str]) -> str:
    """'Sick Leave Policy' -> 'Sick Leave Policy.pdf', path/quote chars out."""
    cleaned = _UNSAFE_FILENAME.sub(" ", (title or "document")).strip()
    return f"{cleaned or 'document'}.pdf"


class KbStorageRepository:
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

    def signed_pdf_url(
        self,
        slug: str,
        ttl: int = SIGNED_URL_TTL,
        download: bool = False,
        download_name: Optional[str] = None,
    ) -> str:
        bounded = self.clamp_ttl(ttl)
        expires = int(time.time()) + bounded
        filename = safe_download_name(download_name)
        signature = self._signature(slug, expires, download, filename)
        query = urlencode({"expires": expires, "download": str(download).lower(), "sig": signature})
        return f"{_PDF_PATH}/{slug}?{query}"

    def read_signed(
        self,
        slug: str,
        expires: int,
        download: bool,
        signature: str,
    ) -> tuple[bytes, str, bool]:
        row = first_of(
            self._database,
            "SELECT title, file_data FROM kb_documents WHERE slug = %s",
            (slug,),
            table="kb_documents",
        )
        if not row:
            raise HTTPException(status_code=404, detail="Knowledge base file not found.")

        filename = safe_download_name(row["title"])
        expected = self._signature(slug, expires, download, filename)
        if expires < int(time.time()) or not hmac.compare_digest(signature, expected):
            raise HTTPException(status_code=404, detail="Knowledge base file not found.")
        if row["file_data"] is None:
            raise HTTPException(status_code=404, detail="Knowledge base file not found.")
        return row["file_data"], filename, download

    @classmethod
    def _signature(cls, slug: str, expires: int, download: bool, filename: str) -> str:
        message = f"{slug}.{expires}.{int(download)}.{filename}".encode()
        return hmac.new(cls._signing_key(), message, hashlib.sha256).hexdigest()
