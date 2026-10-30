"""Knowledge-base document administration: upload, edit, delete.

Bytes live in `kb_documents.data` (PostgreSQL) exactly like seeded docs.
Assistant citations stay in lockstep automatically:

- create / update-with-new-bytes re-cuts the document into citable paragraphs
  — seeded libraries keep the policy-library blocks; admin-uploaded files get
  page paragraphs via app/rag/chunks_from_pdf — and, when the embeddings
  provider key is configured, embeds them and REPLACES `kb_document_chunks`.
- delete removes the document row; its chunks cascade by FK, so the
  assistant can no longer cite a policy that no longer exists.

Without a provider key the document is still saved and searchable — the
assistant simply has no paragraphs to cite for it (replaced store is a no-op).
"""

import io
import re
from typing import Optional

from fastapi import HTTPException

from app.admin.repository import AdminRepository
from app.rag import settings as rag_settings
from app.repositories.base import as_uuid

AUDIENCES = ("employee", "hr")


def _assert_common(title: str, category: str, audience: str) -> None:
    if not title or len(title.strip()) < 3:
        raise HTTPException(status_code=422, detail="Title must be at least 3 characters.")
    if audience not in AUDIENCES:
        raise HTTPException(status_code=422, detail="audience must be 'employee' or 'hr'")
    if category and len(category.strip()) > 60:
        raise HTTPException(status_code=422, detail="Category is limited to 60 characters.")


def _slugify(text: str) -> str:
    base = re.sub(r"\.pdf$", "", (text or "").lower())
    cleaned = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return cleaned[:80] or "untitled-document"


def _pdf_pages(data: bytes) -> Optional[int]:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:
        return None
    try:
        return len(PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return None


def _total(refs: list[str], prefix: str) -> int:
    return len([r for r in refs if r.startswith(prefix)])


class AdminKbDocService:
    def __init__(self, repo: AdminRepository):
        self._repo = repo

    # -- read ----------------------------------------------------------------------

    def list_documents(self) -> list[dict]:
        return [self._out(row) for row in self._repo.list_documents()]

    # -- create ----------------------------------------------------------------------

    def create(
        self,
        *,
        title,
        category,
        audience,
        summary,
        keywords,
        version,
        effective_date,
        filename,
        data: bytes,
    ) -> dict:
        _assert_common(title, category, audience)
        if not data or not data.startswith(b"%PDF"):
            raise HTTPException(status_code=422, detail="A PDF file is required.")
        slug = _slugify(filename or title)
        if self._repo.get_document_meta(slug):
            raise HTTPException(
                status_code=409, detail=f"A document with slug '{slug}' already exists."
            )
        prefix = f"KB-{audience.upper()}-"
        refs = [row.get("ref") or "" for row in self._repo.list_documents()]
        row = self._repo.insert_document(
            {
                "slug": slug,
                "ref": f"{prefix}{_total(refs, prefix) + 1:02d}",
                "title": title.strip(),
                "category": (category or "General").strip(),
                "audience": audience,
                "summary": (summary or "").strip(),
                "keywords": (keywords or "").strip(),
                "version": (version or "v1.0").strip(),
                "effective_date": effective_date or None,
                "data": data,
                "content_type": "application/pdf",
                "file_size": len(data),
                "page_count": _pdf_pages(data),
            }
        )
        self._refresh_chunks(row, data)
        return self._out(self._repo.get_document_meta(slug) or row)

    # -- edit ----------------------------------------------------------------------

    def update(
        self,
        slug: str,
        *,
        title=None,
        category=None,
        audience=None,
        summary=None,
        keywords=None,
        version=None,
        effective_date=None,
        filename=None,
        data: Optional[bytes] = None,
    ) -> dict:
        row = self._repo.get_document_meta(slug)
        if not row:
            raise HTTPException(status_code=404, detail="Unknown knowledge-base document")
        patch: dict = {}
        if title is not None:
            _assert_common(title, category or "", row["audience"])
            patch["title"] = title.strip()
        if category is not None:
            patch["category"] = (category or "General").strip()[:60]
        if audience is not None:
            if audience not in AUDIENCES:
                raise HTTPException(status_code=422, detail="audience must be 'employee' or 'hr'")
            patch["audience"] = audience
        for key in ("summary", "keywords", "version"):
            if locals()[key] is not None:
                patch[key] = (locals()[key] or "").strip() or None
        if effective_date is not None:
            patch["effective_date"] = effective_date or None
        self._repo.update_document(slug, patch, data=data)
        if data:
            merged = {**row, **patch, "file_size": len(data)}
            self._refresh_chunks(merged, data)
        else:
            self._repo.touch_document(slug)
        return self._out(self._repo.get_document_meta(slug))

    # -- delete ----------------------------------------------------------------------

    def delete(self, slug: str) -> dict:
        row = self._repo.get_document_meta(slug)
        if not row:
            raise HTTPException(status_code=404, detail="Unknown knowledge-base document")
        self._repo.delete_document(slug)  # chunks cascade (FK ON DELETE CASCADE)
        return self._out(row)

    # -- internals -----------------------------------------------------------------------

    def _refresh_chunks(self, row: dict, data: bytes) -> None:
        """Replace the document's citable paragraphs in one round trip."""
        from app.rag import embeddings
        from app.rag.chunks_from_pdf import paragraphs_from_pdf

        chunk_dicts = []
        block_no = 0
        for page_no, paragraphs in paragraphs_from_pdf(data):
            for paragraph in paragraphs:
                block_no += 1
                chunk_dicts.append(
                    {
                        "document_slug": row["slug"],
                        "ref": row.get("ref") or "",
                        "title": row.get("title") or "",
                        "audience": row["audience"],
                        "section": f"Page {page_no}",
                        "block_no": block_no,
                        "body": paragraph,
                        "embedding_text": f"{row.get('title') or ''} — 'Page {page_no}': {paragraph}",
                    }
                )
        if not chunk_dicts or not rag_settings.GEMINI_API_KEY:
            # No key (or nothing cut): keep the store consistent by REMOVING
            # any stale paragraphs — never insert chunks without embeddings.
            self._repo.replace_chunks(as_uuid(row["id"]), row, [])
            return
        vectors = embeddings.embed_texts([c["embedding_text"] for c in chunk_dicts])
        for chunk, vector in zip(chunk_dicts, vectors):
            chunk["embedding"] = vector
        self._repo.replace_chunks(as_uuid(row["id"]), row, chunk_dicts)

    @staticmethod
    def _out(row: dict) -> dict:
        return {
            "slug": row["slug"],
            "ref": row.get("ref"),
            "title": row.get("title"),
            "category": row.get("category", "General"),
            "audience": row.get("audience"),
            "summary": row.get("summary", ""),
            "keywords": [k.strip() for k in (row.get("keywords") or "").split(",") if k.strip()],
            "version": row.get("version", "v1.0"),
            "effectiveDate": row.get("effective_date"),
            "fileSize": row.get("file_size"),
            "pages": row.get("page_count"),
            "updatedAt": row.get("updated_at"),
        }
