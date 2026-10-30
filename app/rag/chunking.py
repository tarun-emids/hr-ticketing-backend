"""Pure chunking rules: knowledge-base blocks -> citable paragraph chunks.

The seed content lives in app/kb_seed as typed blocks:

    ("h", text)                   numbered section heading
    ("h2", text)                  sub-heading inside a section
    ("p", text)                   paragraph
    ("bullets", [items])          dash list
    ("table", [head], [rows])     bordered table
    ("note", text)                highlighted call-out

Chunks are the CITATION unit: one row per meaningful block, each carrying the
section heading it sits under and a 1-based block number, so an answer can
cite an exact paragraph of an exact policy ("KB-E-01 ¶7 — '3. Your first
days'"). Headings alone are never chunks: they label the chunks that follow.
Pure rules only — no DB, no network (unit-tested directly).
"""

from typing import Any

_EMBED_LABEL_WIDTH = 120


def chunks_from_document(doc: dict) -> list[dict]:
    """Chunks for one app/kb_seed document, in reading order."""
    built: list[dict] = []
    section = ""  # most recent heading ("h" or "h2") above the block
    block_no = 0
    for block in doc["blocks"]:
        kind, payload = block[0], block[1]
        if kind == "h":  # top-level heading defines the section name
            section = payload
            continue
        if kind == "h2":  # sub-heading refines it
            section = payload
            continue
        body = _block_text(kind, payload, block[2] if kind == "table" and len(block) > 2 else None)
        if not body.strip():
            continue
        block_no += 1
        built.append(_chunk(doc, section, block_no, body))
    return built


def _block_text(kind: str, payload: Any, extra: Any) -> str:
    """Flatten one block to citation-friendly text (same shapes the PDF
    renderer consumes — keep in sync with app/kb_seed/docstrings)."""
    if kind in ("p", "note"):
        return payload
    if kind == "bullets":
        return "\n".join(f"- {item}" for item in payload)
    if kind == "table":
        head, rows = payload, extra or []
        lines = [f"Table: {' | '.join(str(c) for c in head)}"]
        lines.extend(" | ".join(str(cell) for cell in row) for row in rows)
        return "\n".join(lines)
    return ""


def _chunk(doc: dict, section: str, block_no: int, body: str) -> dict:
    """Chunk shape shared by the seeder and the retriever. `embedding_text`
    carries the document context (title + section) so policies that use
    similar words still rank apart; `body` stays the pure quotable text."""
    section_label = f"'{section}'" if section else "introduction"
    return {
        "document_slug": doc["slug"],
        "ref": doc["ref"],
        "title": doc["title"],
        "audience": doc["audience"],
        "section": section if section else "introduction",
        "block_no": block_no,
        "body": body,
        "embedding_text": (f"{doc['title']} — {section_label}: {body}"),
    }


def full_citation(ref: str, title: str, section: str, block_no: int) -> str:
    """Human-readable label for one cited paragraph (sources lists)."""
    return f"{ref} · '{title}' · {section} · ¶{block_no}"


def cite_label(chunk: dict) -> str:
    """Label built straight from a stored/ready chunk (no manual re-typing)."""
    return full_citation(chunk["ref"], chunk["title"], chunk["section"], chunk["block_no"])


def truncate(text: str, limit: int = _EMBED_LABEL_WIDTH) -> str:
    """Snippet cap for sources cards/UI preview text."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
