#!/usr/bin/env python
"""Render and seed the knowledge-base PDFs and metadata into PostgreSQL."""

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kb_seed import normalize, validate  # noqa: E402

PDF_DIR = REPO_ROOT / "scripts" / "knowledge_base_pdfs"


def pick_logo(override: str = "") -> str | None:
    """Use an optional cover logo, or render a branded-text cover."""
    for path in (override, os.getenv("HR_PDF_LOGO", "")):
        if path and Path(path).exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true", help="render PDFs without database writes"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-render even if bytes are unchanged"
    )
    parser.add_argument("--only", default="", help="substring filter on slug")
    parser.add_argument("--logo", default="", help="path to an optional cover logo")
    parser.add_argument(
        "--rows-only",
        action="store_true",
        help="update metadata while keeping any existing PDF bytes unchanged",
    )
    args = parser.parse_args()

    docs = [doc for doc in normalize() if args.only.lower() in doc["slug"]]
    problems = validate()
    if problems:
        print("Seed data validation failed:")
        for problem in problems:
            print(f"  - {problem}")
        return 2

    try:
        from app.kb_seed.render import render_document
    except ImportError as error:
        print("PDF renderer unavailable:", error)
        print("Install the seed tooling first:  pip install -r scripts/requirements-seed.txt")
        return 2

    repository = None
    close_database = None
    if not args.dry_run:
        try:
            from app.config import close_database as close_pool
            from app.config import get_database
            from app.repositories.kb_repository import KbRepository

            repository = KbRepository(get_database())
            close_database = close_pool
        except Exception as error:
            print("PostgreSQL is not available:", error)
            print("Configure DATABASE_URL in .env and apply schema.sql before seeding.")
            return 2

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    logo = pick_logo(args.logo)
    rendered = seeded = failed = 0
    try:
        for doc in docs:
            pdf_bytes, pages = render_document(doc, logo)
            out_path = PDF_DIR / doc["file_name"]
            changed = not out_path.exists() or out_path.read_bytes() != pdf_bytes
            if changed or args.force:
                out_path.write_bytes(pdf_bytes)
                rendered += 1
            print(
                f"  {doc['ref']:>9}  {doc['title'][:58]:<58} pages={pages:>3} "
                f"{'REWRITTEN' if changed else 'unchanged'}"
            )

            if repository is None:
                continue
            try:
                if args.rows_only and not repository.has_pdf(doc["slug"]):
                    raise RuntimeError("no existing PostgreSQL PDF bytes to preserve")
                _seed_row(repository, doc, pdf_bytes, pages, upload=not args.rows_only)
                seeded += 1
            except Exception as error:
                failed += 1
                print(
                    f"  !! failed to seed {doc['ref']} ({type(error).__name__}); "
                    "re-run after resolving the database error"
                )

        mode = "metadata row(s) updated" if args.rows_only else "document(s) synced to PostgreSQL"
        print(
            f"\n{len(docs)} documents · {rendered} PDF file(s) written to {PDF_DIR.name}/"
            f" · {seeded} {mode} · {failed} failed"
        )
        return 1 if failed else 0
    finally:
        if close_database:
            close_database()


def _seed_row(repository, doc: dict, pdf_bytes: bytes, pages: int, *, upload: bool) -> None:
    row = {
        "slug": doc["slug"],
        "ref": doc["ref"],
        "title": doc["title"],
        "category": doc["category"],
        "audience": doc["audience"],
        "summary": doc["summary"],
        "keywords": doc["keywords"],
        "search_text": doc["search_text"],
        "file_path": f"pdf/{doc['file_name']}",
        "file_size": len(pdf_bytes),
        "page_count": pages,
        "version": doc["version"],
        "effective_date": doc["effective_date"],
        "file_data": pdf_bytes if upload else None,
    }
    repository.upsert_document(row)
    print(f"  row synced for {doc['ref']}")


if __name__ == "__main__":
    raise SystemExit(main())
