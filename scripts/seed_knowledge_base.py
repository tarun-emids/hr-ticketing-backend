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
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
import psycopg  # noqa: E402

from app.kb_seed import DOCUMENTS, normalize, validate  # noqa: E402

DEFAULT_PDF_DIR = REPO_ROOT / "scripts" / "knowledge_base_pdfs"
ENV_PATH = REPO_ROOT / ".env"

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
        conn.commit()
    print(f"done: {inserted} inserted / {updated} updated kb_documents rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
