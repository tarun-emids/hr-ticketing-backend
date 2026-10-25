#!/usr/bin/env python
"""Load the knowledge base documents into PostgreSQL: read the pre-rendered
policy PDFs from scripts/knowledge_base_pdfs/, upsert one kb_documents row
each (metadata + `data` bytea + file size) into the DATABASE_URL database
from backend/.env.

Usage — run from the repo root (run schema.sql once first; it creates the
kb_documents table):

    python scripts/seed_knowledge_base.py --dry-run     # plan without touching PostgreSQL
    python scripts/seed_knowledge_base.py               # upsert all documents
    python scripts/seed_knowledge_base.py --only leave  # substring filter on slug
    python scripts/seed_knowledge_base.py --pdf-dir <dir>  # alternate PDF directory

Every run is idempotent: existing slugs are updated in place (content,
metadata, size), new ones inserted. Pre-rendered PDFs live in
scripts/knowledge_base_pdfs/ (committed to the repo) — point --pdf-dir at
another folder only if you render them elsewhere.

When RAG_HF_TOKEN is configured the run ALSO refreshes the assistant's
citable paragraph chunks (kb_document_chunks, embedded with Hugging Face
feature-extraction, app/rag/) for every seeded document. Pass --skip-chunks
to seed only the PDFs, or run without the token to skip chunking with a note.
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402
from psycopg.types.json import Jsonb  # noqa: E402

from app.kb_seed import DOCUMENTS, normalize, validate  # noqa: E402
from app.rag.chunking import chunks_from_document  # noqa: E402
from app.rag.embeddings import embed_texts  # noqa: E402
from app.rag import settings as rag_settings  # noqa: E402

DEFAULT_PDF_DIR = REPO_ROOT / "scripts" / "knowledge_base_pdfs"
ENV_PATH = REPO_ROOT / ".env"

CHUNK_INSERT_SQL = """
    INSERT INTO kb_document_chunks (
        document_id, document_slug, ref, title, audience,
        section, block_no, body, embedding
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
"""  # rows are DELETEd per document first, so this stays a plain insert
UPSERT_SQL = """
    INSERT INTO kb_documents (
        slug, ref, title, category, audience, summary, keywords,
        search_text, data, content_type, file_size, page_count, version, effective_date
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (slug) DO UPDATE SET
        ref = EXCLUDED.ref,
        title = EXCLUDED.title,
        category = EXCLUDED.category,
        audience = EXCLUDED.audience,
        summary = EXCLUDED.summary,
        keywords = EXCLUDED.keywords,
        search_text = EXCLUDED.search_text,
        data = EXCLUDED.data,
        content_type = EXCLUDED.content_type,
        file_size = EXCLUDED.file_size,
        page_count = EXCLUDED.page_count,
        version = EXCLUDED.version,
        effective_date = EXCLUDED.effective_date,
        updated_at = now()
"""


def read_pdf(pdf_dir: Path, file_name: str):
    path = pdf_dir / file_name
    if not path.exists():
        return None
    return path.read_bytes()


def database_url() -> str:
    load_dotenv(ENV_PATH)
    from app import config  # local import: config reads the same .env

    url = config.DATABASE_URL
    if not url:
        raise SystemExit(
            "DATABASE_URL is empty. Open backend/.env and paste the PostgreSQL "
            "credentials, e.g."
            "  DATABASE_URL=postgresql://user:password@host:5432/hrdesk?connect_timeout=10"
        )
    return url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print the plan without touching the DB")
    parser.add_argument("--only", default="", help="substring filter on slug")
    parser.add_argument("--pdf-dir", default="", help="alternate directory containing the PDFs")
    parser.add_argument(
        "--skip-chunks",
        action="store_true",
        help="seed only the PDF documents; skip embedding paragraphs for the assistant",
    )
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir) if args.pdf_dir else DEFAULT_PDF_DIR
    selected = [d for d in normalize() if args.only.lower() in d["slug"].lower()]
    validate()

    missing = []
    plan = []
    for doc in selected:
        pdf_bytes = read_pdf(pdf_dir, doc["file_name"])
        if pdf_bytes is None:
            missing.append(doc["file_name"])
            continue
        plan.append((doc, pdf_bytes, len(pdf_bytes)))

    print(f"{len(plan)} document(s) ready, {len(missing)} missing")
    for file_name in missing:
        print(f"  !! missing: {file_name} (search scripts/knowledge_base_pdfs/ or pass --pdf-dir)")
    if args.dry_run:
        for doc, _, size in plan:
            print(f"  would upsert {doc['ref']} {doc['title']} ({size} bytes)")
        return 0
    if not plan:
        return 1

    inserted, updated = 0, 0
    with psycopg.connect(database_url()) as conn:
        with conn.cursor() as cur:
            existing = {
                row[0]
                for row in cur.execute("SELECT slug FROM kb_documents").fetchall()
            }
            for doc, pdf_bytes, size in plan:
                cur.execute(
                    UPSERT_SQL,
                    (
                        doc["slug"], doc["ref"], doc["title"], doc["category"],
                        doc["audience"], doc["summary"], doc["keywords"],
                        doc["search_text"], pdf_bytes, "application/pdf", size,
                        None, doc.get("version", "v1.0"), doc["effective_date"],
                    ),
                )
                updated += 1 if doc["slug"] in existing else 0
                inserted += 0 if doc["slug"] in existing else 1
            print(f"rows updated: {updated}, rows inserted: {inserted}")
            if args.skip_chunks:
                print("--skip-chunks set: assistant paragraphs not touched")
            elif not rag_settings.HF_TOKEN:
                print(
                    "RAG_HF_TOKEN not set: assistant paragraphs skipped "
                    "(the assistant answers 'not configured'; rerun with the "
                    "token to enable it)"
                )
            else:
                ids = {
                    slug: doc_id
                    for slug, doc_id in cur.execute(
                        "SELECT slug, id FROM kb_documents"
                    ).fetchall()
                }
                _seed_chunks(cur, plan, ids)
        conn.commit()
    print(f"done: {inserted} inserted / {updated} updated kb_documents rows")
    return 0


def _seed_chunks(cur, plan: list, ids: dict) -> None:
    """Refresh the assistant's citable paragraph store for every document.

    Per document: cut blocks into citation chunks (app/rag/chunking),
    embed each chunk once, then REPLACE the document's rows — so a partially
    seeded library can never mix old and new content. One embedding failure
    leaves that document (and the rest) intact and the run still reports it.
    """
    embedded = failed = 0
    for doc, _, _ in plan:
        chunks = chunks_from_document(doc)
        if not chunks:
            continue
        document_id = ids.get(doc["slug"])
        if document_id is None:
            print(f"  !! missing document id for {doc['ref']} — chunks skipped")
            failed += 1
            continue
        try:
            vectors = embed_texts([chunk["embedding_text"] for chunk in chunks])
        except Exception as exc:  # embedder maps provider errors to user text
            print(f"  !! embedding failed for {doc['ref']}: {exc}")
            failed += 1
            continue
        cur.execute("DELETE FROM kb_document_chunks WHERE document_id = %s", (document_id,))
        cur.executemany(
            CHUNK_INSERT_SQL,
            [
                (
                    document_id,
                    doc["slug"],
                    doc["ref"],
                    doc["title"],
                    doc["audience"],
                    chunk["section"],
                    chunk["block_no"],
                    chunk["body"],
                    Jsonb(vector),
                )
                for chunk, vector in zip(chunks, vectors)
            ],
        )
        embedded += 1
        print(f"  chunks refreshed for {doc['ref']}: {len(chunks)} paragraphs")
    print(f"assistant chunks: {embedded} docs embedded, {failed} failed")


if __name__ == "__main__":
    raise SystemExit(main())
