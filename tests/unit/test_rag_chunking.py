"""Pure assistant rules: block -> citable chunk conversion (app/rag/chunking).

No DB, no network — the same seam as test_kb_search.py: everything the
citation promise depends on is pinned here before it can drift.
"""

from app.rag.chunking import chunks_from_document, full_citation, truncate


def doc(**over):
    base = {
        "slug": "leave-and-time-off-policy",
        "ref": "KB-E-01",
        "title": "Leave and Time Off Policy",
        "audience": "employee",
    }
    base.update(over)
    return base


def test_blocks_become_citation_chunks_in_reading_order():
    chunks = chunks_from_document(
        doc(
            blocks=[
                ("p", "Intro paragraph."),
                ("h", "1. Scope"),
                ("p", "Scope paragraph one."),
                ("p", "Scope paragraph two."),
                ("note", "Call-out note."),
            ]
        )
    )
    assert [(c["section"], c["block_no"]) for c in chunks] == [
        ("introduction", 1),  # the leading paragraph sits before any heading
        ("1. Scope", 2),
        ("1. Scope", 3),
        ("1. Scope", 4),  # note is numbered like every other block
    ]


def test_headings_are_never_chunks_themselves():
    chunks = chunks_from_document(doc(blocks=[("h", "1. Scope"), ("h2", "1.1 Eligibility")]))
    assert chunks == []  # headings only label; nothing to cite on their own


def test_bullets_flatten_into_one_citable_list_chunk():
    chunks = chunks_from_document(
        doc(blocks=[("h", "2. Values"), ("bullets", ["Own it.", "Grow by growing others."])])
    )
    assert len(chunks) == 1
    assert chunks[0]["body"] == "- Own it.\n- Grow by growing others."
    assert chunks[0]["block_no"] == 1
    assert chunks[0]["section"] == "2. Values"


def test_table_blocks_keep_header_and_rows():
    chunks = chunks_from_document(
        doc(
            blocks=[
                ("table", ["Expense", "Limit"], [[("Monitor", 15000), ("Desk", 5000)]]),
            ]
        )
    )
    assert len(chunks) == 1
    assert "Table: Expense | Limit" in chunks[0]["body"]
    assert "Monitor | 15000" in chunks[0]["body"]
    assert "Desk | 5000" in chunks[0]["body"]


def test_embedding_text_carries_title_and_section():
    chunks = chunks_from_document(doc(blocks=[("h", "3. Carryover"), ("p", "PTO carries over.")]))
    assert chunks[0]["embedding_text"].startswith("Leave and Time Off Policy — '3. Carryover':")
    assert chunks[0]["body"] == "PTO carries over."  # body stays the quotable text


def test_citation_label_is_ref_title_section_block():
    label = full_citation("KB-E-01", "Leave and Time Off Policy", "3. Carryover", 7)
    assert label == "KB-E-01 · 'Leave and Time Off Policy' · 3. Carryover · ¶7"


def test_snippet_truncation_is_bounded():
    assert truncate("x" * 300, 220).endswith("…")
    assert len(truncate("x" * 300, 220)) <= 220
    assert truncate("short", 220) == "short"
