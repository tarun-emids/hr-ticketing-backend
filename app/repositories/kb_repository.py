"""Knowledge-base metadata and PostgreSQL-backed PDF records."""

from typing import Optional, Sequence

from psycopg_pool import ConnectionPool

from app.repositories.base import first_of, rows_of, run

_DOCUMENT_COLUMNS = (
    "slug, ref, title, category, audience, summary, keywords, search_text, "
    "file_path, file_size, page_count, version, effective_date, updated_at"
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
            f"SELECT {_DOCUMENT_COLUMNS} FROM kb_documents "
            f"WHERE audience IN ({placeholders}) ORDER BY updated_at DESC LIMIT %s",
            (*audiences, limit),
            table="kb_documents",
        )

    def get_by_slug(self, slug: str) -> Optional[dict]:
        return first_of(
            self._database,
            f"SELECT {_DOCUMENT_COLUMNS} FROM kb_documents WHERE slug = %s LIMIT 1",
            (slug,),
            table="kb_documents",
        )

    def has_pdf(self, slug: str) -> bool:
        row = first_of(
            self._database,
            "SELECT file_data IS NOT NULL AS has_pdf FROM kb_documents WHERE slug = %s",
            (slug,),
            table="kb_documents",
        )
        return bool(row and row["has_pdf"])

    def upsert_document(self, row: dict) -> None:
        columns = (
            "slug",
            "ref",
            "title",
            "category",
            "audience",
            "summary",
            "keywords",
            "search_text",
            "file_path",
            "file_size",
            "page_count",
            "version",
            "effective_date",
            "file_data",
        )
        names = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        updates = ", ".join(
            f"{column} = EXCLUDED.{column}"
            for column in columns
            if column not in {"slug", "file_data"}
        )
        run(
            self._database,
            f"INSERT INTO kb_documents ({names}) VALUES ({placeholders}) "
            f"ON CONFLICT (slug) DO UPDATE SET {updates}, "
            "file_data = COALESCE(EXCLUDED.file_data, kb_documents.file_data), "
            "updated_at = now()",
            tuple(row.get(column) for column in columns),
            fetch="none",
            table="kb_documents",
        )
