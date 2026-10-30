"""Admin SQL: account administration, KB document administration, and the
ticket row scan the analytics layer aggregates on.

Three surfaces share one file because they are the same concern — the admin
console's data access — while analytics MATH stays pure in analytics.py.
Plain parameterized SQL only (same dialect subset as every other
repository, so the offline SQLite double executes it verbatim).
"""

from typing import Optional

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.repositories.base import (
    insert_many_rows,
    insert_row,
    as_uuid,
    rows_of,
    run,
)

# Receipt columns of a ticket: everything the analytics rules need.
_TICKET_COLUMNS = (
    "id, ref, employee_id, assignee_id, category, priority, status, subject,"
    " created_at, updated_at, first_reply_at, resolved_at, closed_by"
)

DOC_META_COLUMNS = (
    "id, slug, ref, title, category, audience, summary, keywords, version,"
    " effective_date, file_size, page_count, created_at, updated_at"
)


class AdminRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    # -- tickets (scan is small-bounded; aggregation stays in analytics.py) --

    def ticket_rows(self, limit: int = 5000) -> list[dict]:
        return rows_of(
            self._database,
            f"SELECT {_TICKET_COLUMNS} FROM tickets ORDER BY created_at LIMIT %s",
            (limit,),
            table="tickets",
        )

    # -- accounts -------------------------------------------------------------

    def admin_count(self) -> int:
        row = run(
            self._database,
            "SELECT count(*) AS admins FROM users WHERE role = 'admin'",
            fetch="one",
            table="users",
        )
        return int(row["admins"])

    def open_assigned_count(self, user_id: str) -> int:
        row = run(
            self._database,
            "SELECT count(*) AS open FROM tickets"
            " WHERE assignee_id = %s AND status NOT IN ('Resolved', 'Closed')",
            (as_uuid(user_id),),
            fetch="one",
            table="tickets",
        )
        return int(row["open"])

    def reply_author_count(self, user_id: str) -> int:
        row = run(
            self._database,
            "SELECT count(*) AS replies FROM replies WHERE author_id = %s",
            (as_uuid(user_id),),
            fetch="one",
            table="replies",
        )
        return int(row["replies"])

    def ticket_references_count(self, user_id: str) -> int:
        """Tickets where the account is the employee, assignee or closer —
        the delete guard (history is never destroyed for a real person)."""
        row = run(
            self._database,
            "SELECT count(*) AS refs FROM tickets"
            " WHERE employee_id = %s OR assignee_id = %s OR closed_by = %s",
            (as_uuid(user_id),) * 3,
            fetch="one",
            table="tickets",
        )
        return int(row["refs"])

    def insert_account(self, row: dict) -> dict:
        return insert_row(self._database, "users", row)

    def set_role(self, user_id: str, role: str) -> dict:
        run(
            self._database,
            "UPDATE users SET role = %s WHERE id = %s",
            (role, as_uuid(user_id)),
            fetch="none",
            table="users",
        )
        return self.get_account(user_id)  # freshly read (tests included)

    def get_account(self, user_id: str) -> Optional[dict]:
        return run(
            self._database,
            "SELECT id, name, email, role, password_hash FROM users WHERE id = %s",
            (as_uuid(user_id),),
            fetch="one",
            table="users",
        )

    def delete_account(self, user_id: str) -> None:
        run(
            self._database,
            "DELETE FROM users WHERE id = %s",
            (as_uuid(user_id),),
            fetch="none",
            table="users",
        )

    # -- knowledge-base documents (metadata; bytes loaded only on write) ------

    def list_documents(self) -> list[dict]:
        return rows_of(
            self._database,
            f"SELECT {DOC_META_COLUMNS} FROM kb_documents ORDER BY ref, slug",
            table="kb_documents",
        )

    def get_document_meta(self, slug: str) -> Optional[dict]:
        return run(
            self._database,
            f"SELECT {DOC_META_COLUMNS} FROM kb_documents WHERE slug = %s",
            (slug,),
            fetch="one",
            table="kb_documents",
        )

    def get_document_content_size(self, slug: str) -> Optional[int]:
        row = run(
            self._database,
            "SELECT length(data) AS size FROM kb_documents WHERE slug = %s",
            (slug,),
            fetch="one",
            table="kb_documents",
        )
        return row["size"] if row else None

    def insert_document(self, row: dict) -> dict:
        return insert_row(self._database, "kb_documents", row)

    def update_document(self, slug: str, patch: dict, *, data: Optional[bytes] = None) -> None:
        columns = tuple(patch)
        assignments = ", ".join(f"{column} = %s" for column in columns)
        params = tuple(patch[column] for column in columns) + (slug,)
        run(
            self._database,
            f"UPDATE kb_documents SET {assignments} WHERE slug = %s",
            params,
            fetch="none",
            table="kb_documents",
        )
        if data is not None:
            run(
                self._database,
                "UPDATE kb_documents"
                " SET data = %s, file_size = %s, content_type = 'application/pdf'"
                " WHERE slug = %s",
                (data, len(data), slug),
                fetch="none",
                table="kb_documents",
            )

    def delete_document(self, slug: str) -> None:
        # kb_document_chunks cascades by FK — citations die with the document.
        run(
            self._database,
            "DELETE FROM kb_documents WHERE slug = %s",
            (slug,),
            fetch="none",
            table="kb_documents",
        )

    def touch_document(self, slug: str) -> None:
        """Metadata-only edit still bumps updated_at (kb_doc lists order by it)."""
        from datetime import datetime, timezone

        run(
            self._database,
            "UPDATE kb_documents SET updated_at = %s WHERE slug = %s",
            (datetime.now(timezone.utc).isoformat(), slug),
            fetch="none",
            table="kb_documents",
        )

    def replace_chunks(self, document_id: str, document_row: dict, chunks: list[dict]) -> None:
        """DROP + RE-INSERT one document's citable paragraphs (also what the
        seeder does). Run while the embedding vectors ride along in the chunk
        dicts (`embedding` key, wrapped for the jsonb column)."""
        run(
            self._database,
            "DELETE FROM kb_document_chunks WHERE document_id = %s",
            (as_uuid(document_id),),
            fetch="none",
            table="kb_document_chunks",
        )
        if not chunks:
            return
        insert_many_rows(
            self._database,
            "kb_document_chunks",
            [
                {
                    "document_id": document_id,
                    "document_slug": document_row["slug"],
                    "ref": document_row.get("ref") or "",
                    "title": document_row["title"],
                    "audience": document_row["audience"],
                    "section": chunk["section"],
                    "block_no": chunk["block_no"],
                    "body": chunk["body"],
                    "embedding": Jsonb(chunk["embedding"]),
                }
                for chunk in chunks
            ],
        )
