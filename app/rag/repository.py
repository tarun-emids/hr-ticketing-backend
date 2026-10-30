"""RAG persistence: the paragraph-chunk store and the assistant audit rows.

Two SQL surfaces, both plain parameterized statements (same dialect subset as
every other repository — the offline SQLite test double executes the exact
same queries):

    kb_document_chunks  one citable paragraph per row, embedding as a float
                        array stored via psycopg's Jsonb (no pgvector needed;
                        similarity is computed in app/rag/embeddings.py)
    assistant_queries   one row per question actually answered (employee
                        snapshot + question + answer + cited sources). This
                        is an AUDIT trail only — the UI never reads it back,
                        so a reopened chat window starts clean by design.
"""

from typing import Optional

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app.rag.chunking import truncate
from app.repositories.base import insert_row, rows_of

QUESTION_MAX_SNIPPET = 200


class RagRepository:
    def __init__(self, database: ConnectionPool):
        self._database = database

    # -- chunk store (runtime reads; the SEEDER writes via its own SQL) -------

    def chunks_for_audiences(self, audiences: list[str]) -> list[dict]:
        """Every chunk inside the viewer's visibility pools, pre-rounded for
        cosine comparison (a few hundred rows at 30 policies — read them all).
        Unknown/empty roles read nothing, mirroring the KB gate."""
        if not audiences:
            return []
        placeholders = ", ".join(["%s"] * len(audiences))
        rows = rows_of(
            self._database,
            "SELECT document_slug, ref, title, audience, section, block_no, body,"
            f" embedding FROM kb_document_chunks WHERE audience IN ({placeholders})"
            " ORDER BY document_slug, block_no",
            tuple(audiences),
            table="kb_document_chunks",
        )
        # psycopg hands jsonb back parsed; the SQLite double relies on the
        # JSON column converter — normalise both to a float list here.
        for row in rows:
            row["embedding"] = _as_floats(row.get("embedding"))
            row["snippet"] = truncate(row["body"], QUESTION_MAX_SNIPPET)
        return rows

    def chunk_count(self, document_slug: str) -> int:
        return len(
            rows_of(
                self._database,
                "SELECT id FROM kb_document_chunks WHERE document_slug = %s",
                (document_slug,),
                table="kb_document_chunks",
            )
        )

    # -- audit rows ------------------------------------------------------------

    def record_query(
        self,
        employee_id: str,
        employee_name: str,
        employee_role: str,
        question: str,
        answer: str,
        citations: list[dict],
    ) -> dict:
        """One row per answered question. `citations` are written verbatim —
        the exact chunks the answer cited (ref/title/section/block/snippet)."""
        return insert_row(
            self._database,
            "assistant_queries",
            {
                "employee_id": employee_id,
                "employee_name": employee_name,
                "employee_role": employee_role,
                "question": question,
                "answer": answer,
                "sources": Jsonb(citations),
            },
        )


def _as_floats(value) -> Optional[list[float]]:
    if value is None:
        return None
    if isinstance(value, str):  # sqlite double may hand back the raw JSON text
        import json

        value = json.loads(value)
    return [float(item) for item in value]
