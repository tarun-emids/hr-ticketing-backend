"""Citable paragraph derivation from an uploaded PDF.

Admin-uploaded/edited documents have no block source in `app/kb_seed` — their
only content is the PDF file itself. This module turns those bytes into the
same paragraph-chunk dictionaries the seeder produces (app/rag/chunking), so
an uploaded policy is cited exactly like a generated one:

    [(page_no, [paragraph, ...]), ...]   1-based page numbers

pypdf is imported lazily: without it (or with a scanned, text-less PDF) the
document saves fine — it just yields no citation chunks.
"""

import io


def paragraphs_from_pdf(data: bytes, min_chars: int = 30) -> list[tuple[int, list[str]]]:
    """[(1, ['...', ...]), ...] per text page (1-based), paragraphs ≥ min_chars."""
    if not data or not data.startswith(b"%PDF"):
        return []
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError:  # optional dependency — documented degradation
        return []
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        return []
    pages = []
    for page_no, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        paragraphs = [
            " ".join(par.split())
            for par in text.split("\n\n")
            if len(" ".join(par.split())) >= min_chars
        ]
        if paras := [par for par in paragraphs if par]:
            pages.append((page_no, paras))
    return pages
