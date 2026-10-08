"""Supabase Storage repository for ticket/draft attachments.

The `ticket-attachments` bucket is private; files are only readable through
short-lived signed URLs the backend signs on demand (service-role key).
This is the boundary that turns storage/network failures into the API's
413/502 responses — services never see storage3 exceptions.
"""
from fastapi import HTTPException

from app.config import ATTACHMENT_BUCKET, MAX_ATTACHMENT_BYTES, SIGNED_URL_TTL, SUPABASE_URL

MB = 1024 * 1024


class AttachmentStorageRepository:
    """Bucket operator. Not a table-backed SupabaseRepository — Storage has a
    different API surface, but it belongs in the same data-access layer."""

    def __init__(self, client):
        self._client = client

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def clamp_ttl(ttl: int) -> int:
        return max(60, min(ttl, 86400))

    # -- operations --------------------------------------------------------

    def upload(self, path: str, data: bytes, content_type: str | None) -> None:
        storage = self._client.storage.from_(ATTACHMENT_BUCKET)
        try:
            storage.upload(
                path,
                data,
                {"contentType": content_type or "application/octet-stream", "upsert": "false"},
            )
        except Exception as e:  # storage3 raises generic StorageException
            raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}")

    def remove(self, path: str) -> None:
        try:
            self._client.storage.from_(ATTACHMENT_BUCKET).remove([path])
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not remove draft attachment: {e}")

    def signed_url(self, path: str, ttl: int = SIGNED_URL_TTL) -> str:
        storage = self._client.storage.from_(ATTACHMENT_BUCKET)
        try:
            res = storage.create_signed_url(path, self.clamp_ttl(ttl))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not sign URL: {e}")

        url = res.get("signedURL") or res.get("signedUrl") or ""
        if url and not url.startswith("http"):
            url = f"{SUPABASE_URL}/storage/v1{url}"
        return url

    # -- validation exposed for services ------------------------------------

    @staticmethod
    def check_size(data: bytes) -> None:
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File is larger than {MAX_ATTACHMENT_BYTES // MB} MB",
            )
