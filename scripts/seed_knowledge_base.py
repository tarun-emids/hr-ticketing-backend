#!/usr/bin/env python
"""Seed the knowledge base: render policy PDFs into scripts/knowledge_base_pdfs/,
upload them into the private `knowledge-base` storage bucket and upsert
their metadata into the `kb_documents` table (backend/.env credentials).

Usage — run from the repo root:

    python scripts/seed_knowledge_base.py --dry-run      # render PDFs only (no Supabase)
    python scripts/seed_knowledge_base.py                # render + upload + upsert
    python scripts/seed_knowledge_base.py --rows-only    # rows only; PDFs were uploaded manually
    python scripts/seed_knowledge_base.py --only leave   # substring filter on slug
    python scripts/seed_knowledge_base.py --force        # re-render even if unchanged

Requires reportlab when documents are rendered (see scripts/requirements-seed.txt):
    pip install -r scripts/requirements-seed.txt

PDFs are re-rendered only when their bytes change, so re-runs are cheap and
safe in cron-like setups. Storage is uploaded with upsert semantics; rows are
select-then-insert/update against the slug so no PostgREST version nuance applies.
"""
import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.kb_seed import DOCUMENTS, normalize, validate  # noqa: E402  (no reportlab needed)

PDF_DIR = REPO_ROOT / "scripts" / "knowledge_base_pdfs"
BUCKET = "knowledge-base"


def pick_logo(override: str = "") -> str | None:
    """Optional cover logo: --logo flag, then HR_PDF_LOGO env. The backend
    repo does not ship frontend assets, so rendering falls back to a plain
    branded-text cover when none is provided."""
    candidates = [override, os.getenv("HR_PDF_LOGO", "")]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="render PDFs only; no Supabase calls")
    parser.add_argument("--force", action="store_true", help="re-render even if bytes are unchanged")
    parser.add_argument("--only", default="", help="substring filter on slug")
    parser.add_argument("--logo", default="", help="path to a small cover logo image (optional)")
    parser.add_argument(
        "--rows-only",
        action="store_true",
        help="only insert/update kb_documents rows — for when the PDFs were "
             "uploaded to the bucket manually in the dashboard",
    )
    args = parser.parse_args()

    docs = [d for d in normalize() if args.only.lower() in d["slug"]]
    problems = validate()
    if problems:
        print("Seed data validation failed:")
        for p in problems:
            print(f"  - {p}")
        return 2

    # The renderer needs reportlab — installed via scripts/requirements-seed.txt
    try:
        from app.kb_seed.render import render_document
    except ImportError as e:
        print("PDF renderer unavailable:", e)
        print("Install the seed tooling first:  pip install -r scripts/requirements-seed.txt")
        return 2

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    logo = pick_logo(args.logo)
    client = None

    if not args.dry_run:
        try:
            from app.config import get_client
            client = get_client()
        except Exception as e:
            print("Supabase client not available:", e)
            print("Copy .env.example to .env and fill SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY, "
                  "or run with --dry-run.")
            return 2
        if not args.rows_only:
            _ensure_bucket(client)

    rendered = seeded = failed = 0
    failures: list[str] = []
    for doc in docs:
        pdf_bytes, pages = render_document(doc, logo)
        out_path = PDF_DIR / doc["file_name"]
        changed = not out_path.exists() or out_path.read_bytes() != pdf_bytes
        if changed or args.force:
            out_path.write_bytes(pdf_bytes)
            rendered += 1
        print(f"  {doc['ref']:>9}  {doc['title'][:58]:<58} pages={pages:>3} "
              f"{'REWRITTEN' if changed else 'unchanged'}")

        if client is not None:
            try:
                _seed_row(client, doc, pdf_bytes, pages, upload=not args.rows_only)
                seeded += 1
            except Exception as e:  # e.g. an httpx.ReadTimeout mid-run
                failed += 1
                note = f"{doc['ref']} — {type(e).__name__}: {e}"
                failures.append(note)
                print(f"  !! network hiccup on {note.split(' — ')[0]} — re-run the same "
                      f"command to resume (row updates are idempotent)")

    mode = "row(s) updated (files untouched)" if args.rows_only else "row(s) synced to Supabase"
    print(f"\n{len(docs)} documents · {rendered} PDF file(s) written to {PDF_DIR.name}/"
          f" · {seeded} {mode} · {failed} failed")
    if failures:
        print("\nNot finished — run the same command again; resumes cleanly:")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


def _bucket_exists(client) -> bool:
    try:
        for b in client.storage.list_buckets() or []:
            if (b.get("name") or b.get("id")) == BUCKET:
                return True
    except Exception:
        return False
    return False


def _ensure_bucket(client) -> None:
    """schema.sql creates the private 'knowledge-base' bucket; the create call
    below is only a safety net, written to tolerate storage3 client versions."""
    if _bucket_exists(client):
        print(f"Bucket '{BUCKET}' already exists")
        return
    problems: list[str] = []
    for kwargs in ({"name": BUCKET, "public": False}, {"name": BUCKET}):
        try:
            client.storage.create_bucket(**kwargs)
            print(f"Created private bucket '{BUCKET}'")
            return
        except TypeError as e:  # this client's create_bucket accepts different kwargs
            problems.append(f"{type(e).__name__}: {e}")
        except Exception as e:
            msg = str(e).lower()
            if any(s in msg for s in ("exist", "duplicate", "conflict", "409", "23505")):
                print(f"Bucket '{BUCKET}' already exists")
                return
            problems.append(f"{type(e).__name__}: {e}")
    if _bucket_exists(client):
        print(f"Bucket '{BUCKET}' already exists")
        return
    raise RuntimeError(
        f"Could not create the '{BUCKET}' bucket. Open the Supabase SQL editor and run "
        "schema.sql once (it creates the bucket among the other tables), then re-run "
        "this seed script. Attempts: " + " | ".join(problems)
    )


def _file_missing(storage, path: str) -> bool:
    """True only when the Storage API clearly reports the object absent."""
    try:
        storage.create_signed_url(path, 60)
        return False
    except Exception as e:
        m = str(e).lower()
        return any(s in m for s in ("not found", "404", "no such", "not_found"))


def _delete_file(storage, file_path: str) -> str | None:
    """Best-effort delete across storage3 version variants. Returns None on
    success (incl. 'file was not there'), else a failure reason."""
    last: Exception | None = None
    for name in ("remove", "delete"):
        method = getattr(storage, name, None)
        if method is None:
            continue
        for arg in ([file_path], file_path):
            try:
                method(arg)
                return None
            except Exception as e:
                last = e
        if last and any(s in str(last).lower() for s in ("not found", "404")):
            return None
    return f"existing file could not be deleted: {last}"


def _upload_file(storage, file_path: str, pdf_bytes: bytes) -> str | None:
    """Upload with upsert semantics, tolerating storage3 client version drift.

    Returns None on success or a human-readable reason. Only signature
    mismatches (TypeError/AttributeError) advance through the attempt chain,
    so genuine storage API errors are reported verbatim.
    """
    attempts = [
        lambda: storage.upload(
            file_path, pdf_bytes, {"contentType": "application/pdf", "upsert": "true"}
        ),
        lambda: storage.upload(file_path, pdf_bytes, upsert=True),
        lambda: storage.upload(file_path, pdf_bytes),
    ]
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            attempt()
            return None
        except (TypeError, AttributeError) as e:
            last_error = e  # wrong call shape for this client version — try next
        except Exception as e:
            msg = str(e).lower()
            if not any(s in msg for s in ("exist", "duplicate", "conflict", "409", "23505")):
                return f"upload: {e}"
            # File exists and this call shape ignores upsert → delete, retry.
            fail = _delete_file(storage, file_path)
            if fail:
                return f"upload: file exists, {fail}"
            try:
                attempt()
                return None
            except Exception as retry_error:
                return f"upload: {retry_error}"
    return f"upload: {last_error}"


def _seed_row(client, doc: dict, pdf_bytes: bytes, pages: int, upload: bool = True) -> None:
    file_name = doc["file_name"]
    file_path = f"pdf/{file_name}"
    if upload:
        storage = client.storage.from_(BUCKET)
        reason = _upload_file(storage, file_path, pdf_bytes)
        if reason:
            print(f"  !! upload failed for {doc['file_name']}: {reason}")
            return
    else:
        # The user uploaded files by hand — find where they actually live.
        storage = client.storage.from_(BUCKET)
        if _file_missing(storage, file_path):
            if _file_missing(storage, file_name):
                print(f"  !! row skipped — {file_name} not found in the bucket "
                      f"(checked pdf/{file_name} and the bucket root). Upload it "
                      f"and re-run --rows-only.")
                return
            file_path = file_name
            print(f"  note: found {file_name} at the bucket root — "
                  f"pointing row at it instead of pdf/{file_name}")

    row = {
        "slug": doc["slug"],
        "ref": doc["ref"],
        "title": doc["title"],
        "category": doc["category"],
        "audience": doc["audience"],
        "summary": doc["summary"],
        "keywords": doc["keywords"],
        "search_text": doc["search_text"],
        "file_path": file_path,
        "file_size": len(pdf_bytes),
        "page_count": pages,
        "version": doc["version"],
        "effective_date": doc["effective_date"].isoformat(),
    }

    existing = client.table("kb_documents").select("id").eq("slug", doc["slug"]).execute()
    data = getattr(existing, "data", None)
    if isinstance(data, tuple) and len(data) == 2:
        data = data[0]
    if data:
        client.table("kb_documents").update(row).eq("slug", doc["slug"]).execute()
        action = "updated"
    else:
        client.table("kb_documents").insert(row).execute()
        action = "inserted"
    print(f"  row {action} for {doc['ref']}")


if __name__ == "__main__":
    raise SystemExit(main())
