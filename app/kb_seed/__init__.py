"""Knowledge base seed data package.

Aggregates the document definitions from the content modules, derives the
search blob (`search_text`) used by the backend scorer, and validates the
dataset before rendering / seeding.
"""
from datetime import date

from .employee_part1 import EMPLOYEE_PART1
from .employee_part2 import EMPLOYEE_PART2
from .employee_part3 import EMPLOYEE_PART3
from .employee_part4 import EMPLOYEE_PART4
from .hr_part1 import HR_PART1
from .hr_part2 import HR_PART2

DOCUMENTS = [
    *EMPLOYEE_PART1,
    *EMPLOYEE_PART2,
    *EMPLOYEE_PART3,
    *EMPLOYEE_PART4,
    *HR_PART1,
    *HR_PART2,
]

AUDIENCES = {"employee", "hr"}


def _flatten_blocks(blocks):
    lines = []
    for block in blocks:
        kind = block[0]
        if kind in ("p", "note", "h", "h2"):
            lines.append(block[1])
        elif kind == "bullets":
            lines.extend(block[1])
        elif kind == "table":
            lines.append(" ".join(block[1]))
            lines.extend(" ".join(str(cell) for cell in row) for row in block[2])
    return " ".join(lines)


def normalize():
    """Fill derived fields on every document (mutates + returns DOCUMENTS)."""
    for doc in DOCUMENTS:
        doc.setdefault("effective", (2026, 1, 1))
        doc["effective_date"] = date(*doc["effective"])
        body = _flatten_blocks(doc["blocks"])
        blob = " ".join([
            doc["title"],
            doc["category"],
            doc["summary"],
            doc["keywords"],
            body,
        ])
        doc["search_text"] = " ".join(blob.lower().split())
        doc["file_name"] = f"{doc['ref'].lower()}-{doc['slug']}.pdf"
    return DOCUMENTS


def validate():
    """Cheap consistency checks; returns a list of human-readable problems."""
    problems = []
    seen_slugs, seen_refs = set(), set()
    for doc in DOCUMENTS:
        tag = f"{doc.get('ref') or doc.get('slug') or '?'}"
        for field in ("slug", "ref", "title", "category", "audience", "summary", "keywords", "blocks"):
            if not doc.get(field):
                problems.append(f"{tag}: missing field '{field}'")
        if doc.get("audience") not in AUDIENCES:
            problems.append(f"{tag}: audience must be 'employee' or 'hr'")
        if not (80 <= len(doc.get("summary", "")) <= 400):
            problems.append(f"{tag}: summary length looks off")
        if doc["slug"] in seen_slugs:
            problems.append(f"{tag}: duplicate slug")
        if doc["ref"] in seen_refs:
            problems.append(f"{tag}: duplicate ref")
        seen_slugs.add(doc.get("slug", ""))
        seen_refs.add(doc.get("ref", ""))
    return problems
