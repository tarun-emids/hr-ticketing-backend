"""Shared Supabase plumbing for all repositories.

supabase-py gotchas baked into this module (moved here from the old
`routers/tickets_core.py`, where every router used to depend on it):

- **Never call `.table("X")` on the result of another `.table("Y")`** — query
  builders are single-use chains; always start a fresh `client.table(name)`.
- **PostgREST response shapes vary by supabase-py version** (APIResponse with
  `.data`, plain lists, single dicts, `(data, count)` tuples). All calls go
  through `run()`/`rows_of()`/`first_of()`/`unwrap()` here, which normalise
  every variant. `.execute().data` or `.single()` chains are used nowhere else.
- Write `.is_("col", None)` (v2 rejects the string `"null"`) for NULL checks.
"""
import re
from typing import Any, Optional

from fastapi import HTTPException
from postgrest.exceptions import APIError

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def unwrap(res: Any):
    """Version-proof PostgREST response handling.

    supabase-py variants return APIResponse objects (with .data), plain lists,
    dicts, or (data, count) tuples depending on installed version — normalise
    all of them to dict/list JSON data here.
    """
    if isinstance(res, tuple) and len(res) == 2:
        return res[0]
    if isinstance(res, (list, dict)):
        return res
    return getattr(res, "data", None)


def run(q):
    """Execute a build, mapping PostgREST errors to HTTP 4xx/5xx-with-detail."""
    try:
        return unwrap(q.execute())
    except APIError as e:
        detail = getattr(e, "message", None) or str(e)
        code = str(getattr(e, "code", "") or "")
        status = 400 if code.startswith("23") else 502
        raise HTTPException(status_code=status, detail=f"Database rejected the write: {detail}")


def rows_of(q) -> list:
    data = run(q)
    if isinstance(data, dict):
        return [data]
    return data or []


def first_of(q) -> Optional[dict]:
    result = rows_of(q)
    return result[0] if result else None


class SupabaseRepository:
    """Base for table-backed repositories.

    Holds the injected client; subclasses expose intent-revealing query
    methods. Every method builds a FRESH `self._client.table(name)` chain —
    see the module docstring for why a builder must never be reused.
    """

    TABLE_NAME: str = ""

    def __init__(self, client):
        # Any supabase-like client works here (tests inject FakeSupabase).
        self._client = client

    def table(self):
        return self._client.table(self.TABLE_NAME)
