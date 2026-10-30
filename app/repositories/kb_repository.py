"""Knowledge base documents (public.kb_documents) in PostgreSQL.

Metadata and the PDF bytes both live in the database: the `data` column keeps
the rendered PDF (loaded by scripts/seed_knowledge_base.py), and read access
is served only through the API's streaming endpoint after the visibility gate.
Repositories stay role-agnostic: callers pass the audience pool(s) the viewer
may read, which the KbService derives from the viewer's role in `users`.
"""

from typing import Optional, Sequence

from psycopg_pool import ConnectionPool

from app.repositories.base import first_of, rows_of

_META_COLUMNS = (
    "slug, ref, title, category, audience, summary, keywords, "
    "version, effective_date, file_size, page_count, updated_at"
)


class KbRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    def list_by_audiences(self, audiences: Sequence[str], limit: int = 200) -> list[dict]:
        """All documents in the viewer's pools, newest-refresh first."""
        if not audiences:
            return []
        placeholders = ", ".join(["%s"] * len(audiences))
        return rows_of(
            self._database,
            f"SELECT {_META_COLUMNS} FROM kb_documents "
            f"WHERE audience IN ({placeholders}) "
            f"ORDER BY updated_at DESC LIMIT %s",
            (*audiences, limit),
            table="kb_documents",
        )

    def get_by_slug(self, slug: str) -> Optional[dict]:
        """Metadata for one document (without the heavy content column)."""
        return first_of(
            self._database,
            f"SELECT {_META_COLUMNS} FROM kb_documents WHERE slug = %s LIMIT 1",
            (slug,),
            table="kb_documents",
        )

    def get_content(self, slug: str) -> Optional[bytes]:
        """PDF bytes for one document — fetched only after the caller's gate."""
        row = first_of(
            self._database,
            "SELECT data FROM kb_documents WHERE slug = %s LIMIT 1",
            (slug,),
            table="kb_documents",
        )
        if not row or row["data"] is None:
            return None
        return bytes(row["data"])
