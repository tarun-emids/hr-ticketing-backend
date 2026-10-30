"""Knowledge base service — viewer roles, visibility pools, weighted search.

Design (carried from the original full-stack implementation, evolved):

- The viewer's role is ALWAYS resolved server-side from public.users — the
  client only sends `viewerId`, which is the same mock-auth stand-in the
  notifications endpoints use until real JWT auth lands. Editing query
  params can therefore never widen what a browser sees.
- Visibility pools:
      employee -> employee-facing policies
      agent    -> employee + hr pools (HR also answers employee questions,
                  so agents legitimately see the public policies)
      admin    -> employee + hr pools (if an admin account is ever
                  provisioned — future-proof mapping)
    Unknown or missing roles see nothing.
- Out-of-pool documents return 403 (they exist, but are not for you);
  unknown slugs return 404. Same gate in front of metadata and file content:
  unlike the token-signed approach, the gate runs on EVERY download request,
  so a link can never outlive the permission check that minted it.
- Search: tokenise the query, score every visible document over weighted
  fields (title 10 > category 6 > keywords 4 > summary 2 > body 1). A token
  must hit a QUALIFIER field (the four above the body blob) to select the
  document — body-only matches are noise ('leave' would otherwise surface
  every policy that once mentions leave). Body hits still add to the score
  for ordering; an exact title-phrase match adds a bonus.

Pure rules (pools, tokenising, scoring, keyword splitting) are module-level
functions; the service class is the only place that talks to repositories.
"""

import re
from typing import Optional

from fastapi import HTTPException

from app.models import kb_doc_out
from app.repositories.base import UUID_RE
from app.repositories.kb_repository import KbRepository
from app.repositories.user_repository import UserRepository

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")

# Characters a Content-Disposition filename should never carry
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def safe_download_name(title: Optional[str]) -> str:
    """'Sick Leave Policy' -> 'Sick Leave Policy.pdf', path/quote chars out."""
    cleaned = _UNSAFE_FILENAME.sub(" ", (title or "document")).strip()
    return f"{cleaned or 'document'}.pdf"

# role -> the document pools it may read
ROLE_POOLS: dict[str, tuple[str, ...]] = {
    "employee": ("employee",),
    "agent": ("employee", "hr"),
    "admin": ("employee", "hr"),
}

SEARCH_RESULT_LIMIT = 3  # top-N matches returned for a query
LIST_LIMIT = 50  # unwalled catalogue page
POPULAR_LIMIT = 8  # dashboard suggestion strip
POOL_FETCH_LIMIT = 200  # full metadata scan cap (≤ few hundred docs)


class KbNotFound(HTTPException):
    def __init__(self, detail: str = "Knowledge base document not found"):
        super().__init__(status_code=404, detail=detail)


class KbForbidden(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=403,
            detail="You don't have permission to view this document.",
        )


class UnknownViewer(HTTPException):
    def __init__(self):
        super().__init__(status_code=404, detail="Unknown viewer")


# ---------------------------------------------------------------------------
# Pure rules (unit-tested directly)
# ---------------------------------------------------------------------------


def pools_for(role: Optional[str]) -> list[str]:
    """The audience pools a role may read; unknown roles read nothing."""
    return list(ROLE_POOLS.get(role or "", ()))


def keywords_out(raw: Optional[str]) -> list[str]:
    """Comma-separated 'keywords' column -> clean list for the API."""
    return [k.strip() for k in (raw or "").split(",") if k.strip()]


def tokenize(q: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (q or "").lower())
    return [t for t in tokens if len(t) > 1]


_WEIGHTS = (
    ("title", 10),
    ("category", 6),
    ("keywords", 4),
    ("summary", 2),
    ("search_text", 1),  # flattened lowercase body blob — ordering only
)
_N_QUALIFIERS = len(_WEIGHTS) - 1
_TITLE_PHRASE_BONUS = 8


def score(row: dict, tokens: list[str], phrase: str) -> Optional[int]:
    """Weighted score of one document for the token set, None when the
    document must not be selected (every token matched only body text)."""
    fields = [(row.get(key) or "").lower() for key, _ in _WEIGHTS]
    total = 0
    for token in tokens:
        best = 0
        qualified = 0
        for i, ((_, weight), text) in enumerate(zip(_WEIGHTS, fields)):
            if token in text:
                best = max(best, weight)
                if i < _N_QUALIFIERS:
                    qualified = max(qualified, weight)
        if qualified == 0:
            return None  # body-only match — not selectable
        total += best
    if phrase and phrase in fields[0]:  # exact phrase bonus on the title
        total += _TITLE_PHRASE_BONUS
    return total


def search_rows(rows: list[dict], q: str) -> list[dict]:
    """Score the visible pool for one query, best-first, title as tiebreak."""
    phrase = (q or "").strip().lower()
    tokens = tokenize(phrase)
    scored: list[tuple[int, dict]] = []
    for row in rows:
        s = score(row, tokens, phrase)
        if s:
            scored.append((s, row))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["title"].lower()))
    return [r for _, r in scored]


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class KbService:
    def __init__(
        self,
        kb: KbRepository,
        users: UserRepository,
    ):
        self._kb = kb
        self._users = users

    # -- viewer + gates ------------------------------------------------------

    def _viewer(self, viewer_id: Optional[str]) -> dict:
        """Resolve viewerId to a real account row (mock-auth stand-in; the
        role that comes back is the ONLY trust anchor for visibility)."""
        if not viewer_id or not UUID_RE.match(viewer_id):
            raise HTTPException(status_code=422, detail="viewerId (uuid) is required")
        viewer = self._users.get_by_id(viewer_id)
        if not viewer:
            raise UnknownViewer()
        return viewer

    def _pools(self, viewer: dict) -> list[str]:
        return pools_for(viewer.get("role"))

    def _visible_rows(self, viewer: dict) -> list[dict]:
        return self._kb.list_by_audiences(self._pools(viewer), limit=POOL_FETCH_LIMIT)

    def _doc_or_gate(self, slug: str, viewer: dict) -> dict:
        """404 unknown slug, 403 known-but-out-of-pool — one gate shared by
        the metadata and file-URL endpoints."""
        if not SLUG_RE.match(slug or ""):
            raise KbNotFound()
        row = self._kb.get_by_slug(slug)
        if not row:
            raise KbNotFound()
        if row["audience"] not in self._pools(viewer):
            raise KbForbidden()  # exists, but not for this viewer's eyes
        return row

    # -- endpoint cores ------------------------------------------------------

    def list_or_search(self, viewer_id: Optional[str], q: str = "") -> list[dict]:
        """GET /kb — catalogue page; with q, the top few scored matches."""
        viewer = self._viewer(viewer_id)
        rows = self._visible_rows(viewer)
        if q and q.strip():
            return [kb_doc_out(r) for r in search_rows(rows, q)[:SEARCH_RESULT_LIMIT]]
        return [kb_doc_out(r) for r in rows[:LIST_LIMIT]]

    def popular(self, viewer_id: Optional[str]) -> list[dict]:
        """GET /kb/popular — the most recently refreshed documents in the
        viewer's pools, for the dashboard suggestion strip."""
        viewer = self._viewer(viewer_id)
        return [kb_doc_out(r) for r in self._visible_rows(viewer)[:POPULAR_LIMIT]]

    def get_document(self, slug: str, viewer_id: Optional[str]) -> dict:
        """GET /kb/{slug} — metadata for one document, after the gate."""
        viewer = self._viewer(viewer_id)
        return kb_doc_out(self._doc_or_gate(slug, viewer))

    def file_get(
        self,
        slug: str,
        viewer_id: Optional[str],
        download: bool = False,
    ) -> tuple[bytes, str]:
        """GET /kb/{slug}/file — the PDF bytes themselves, behind the same
        visibility gate (the gate re-checks the viewer on every fetch, so an
        old link that someone kept cannot outlive a permission change).
        download=True returns an attachment filename suggestion; the default
        renders inline."""
        viewer = self._viewer(viewer_id)
        row = self._doc_or_gate(slug, viewer)
        data = self._kb.get_content(slug)
        if data is None:
            # Seeded document whose PDF bytes were never loaded (or removed).
            raise HTTPException(
                status_code=502,
                detail="Document content could not be loaded — ask HR to re-seed it.",
            )
        return {"data": data, "filename": safe_download_name(row.get("title"))}
