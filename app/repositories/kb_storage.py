"""Supabase Storage repository for knowledge-base policy PDFs.

The `knowledge-base` bucket is private (service-role only); every read is a
short-lived signed URL minted on demand. One signing surface, two flavours:

    view      — no transform: the browser renders the PDF inline (iframe /
                new tab). The old implementation signed a `download` URL for
                both purposes, which decays to a forced attachment download
                and can never display inline; view/download are separated
                here on purpose.
    download  — `download` transform with a suggested filename, so the
                browser's save dialog proposes 'Title.pdf' instead of a
                signed-object hash.

Version-tolerant like the rest of the sealed edges: older storage clients
without the options parameter degrade to a plain sign. Signing is a replayable
read (app/retries.py) riding on the shared storage circuit breaker
(app/resilience.py).
"""
import re
from typing import Optional

from fastapi import HTTPException

from app import config as app_config
from app.config import KB_BUCKET, SIGNED_URL_TTL
from app.resilience import CircuitOpenError, storage_breaker
from app.retries import READ, retry_call

# Characters a Content-Disposition filename should never carry
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_download_name(title: Optional[str]) -> str:
    """'Sick Leave Policy' -> 'Sick Leave Policy.pdf', path/quote chars out."""
    cleaned = _UNSAFE_FILENAME.sub(" ", (title or "document")).strip()
    return f"{cleaned or 'document'}.pdf"


class KbStorageRepository:
    """Storage operator for the KB bucket — same boundary role as
    AttachmentStorageRepository, different bucket + signing options."""

    def __init__(self, client):
        self._client = client

    @staticmethod
    def clamp_ttl(ttl: int) -> int:
        return max(60, min(ttl, 86400))

    def signed_pdf_url(
        self,
        path: str,
        ttl: int = SIGNED_URL_TTL,
        download: bool = False,
        download_name: Optional[str] = None,
    ) -> str:
        """Signed URL for one policy PDF; with download=True the response is
        marked as an attachment carrying the suggested filename."""
        storage = self._client.storage.from_(KB_BUCKET)
        bounded = self.clamp_ttl(ttl)
        options = None
        if download:
            options = {"download": download_name or safe_download_name(None)}

        def _sign():
            if options is not None:
                try:
                    return storage_breaker.call(
                        lambda: storage.create_signed_url(path, bounded, options)
                    )
                except TypeError:
                    # Older storage client without the options parameter —
                    # degrade to a plain sign (link still works, browser
                    # just picks the raw object name for 'save as').
                    return storage_breaker.call(
                        lambda: storage.create_signed_url(path, bounded)
                    )
            return storage_breaker.call(lambda: storage.create_signed_url(path, bounded))

        try:
            res = retry_call(_sign, mode=READ)
        except CircuitOpenError:
            raise HTTPException(
                status_code=503,
                detail="Attachment storage is temporarily unavailable — try again shortly.",
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not sign URL: {e}")

        url = (res.get("signedURL") if isinstance(res, dict) else None) or ""
        if url and not url.startswith("http"):
            url = f"{app_config.SUPABASE_URL}/storage/v1{url}"
        return url
