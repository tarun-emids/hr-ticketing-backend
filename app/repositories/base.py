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

Every PostgREST execution goes through `run()`, so that is also where the
semantic db span lives (no-op when tracing is off): the span name carries
the operation and, when readable, the table — the actual HTTP hop remains
visible in the httpx client span nested inside it.
"""
import re
from typing import Any, Optional

from fastapi import HTTPException
from postgrest.exceptions import APIError

from app.observability import db_span
from app.resilience import db_breaker, CircuitOpenError

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _db_failure(e: BaseException) -> bool:
    """Breaker classification: is this PostgREST outcome an OUTAGE signal?

    Postgres constraint violations (code 23xxx) are the CALLER's fault —
    the API already answers them 400 — so they are neutral for the breaker;
    a stream of those must never slowly trip the circuit.
    Any other APIError plus every non-APIError exception (timeouts,
    connection errors) is already mapped to 502 today, i.e. the shared
    dependency failing: those count.
    """
    if isinstance(e, APIError):
        return not str(getattr(e, "code", "") or "").startswith("23")
    return True


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


def _builder_op(builder) -> str:
    """Best-effort PostgREST operation name from the builder class (version-
    dependent surface, hence non-fatal): SelectBuilder -> "select", etc."""
    name = type(builder).__name__.lower()
    if name.endswith("builder"):
        name = name[: -len("builder")]
    return name or "query"


def _builder_table(builder) -> Optional[str]:
    """Best-effort table name (attribute names differ across versions)."""
    for attr in ("table_name", "_table_name", "table", "source"):
        val = getattr(builder, attr, None)
        if isinstance(val, str) and val:
            return val
    return None


def run(q):

"""Execute a build behind the db circuit breaker, mapping PostgREST errors
to HTTP 4xx/5xx-with-detail.
"""
op = _builder_op(q)
table = _builder_table(q)
span_name = f"db.postgrest.{table}.{op}" if table else f"db.postgrest.{op}"
attrs = {"db.system": "postgres", "db.operation": op}
if table:
    attrs["db.postgrest.table"] = table

try:
    with db_span(span_name, attrs):
        return unwrap(db_breaker.call(q.execute, is_failure=_db_failure))
except CircuitOpenError:
    raise HTTPException(
        status_code=503,
        detail="Database is temporarily unavailable — try again shortly.",
    )
except APIError as e:
    detail = getattr(e, "message", None) or str(e)
    code = str(getattr(e, "code", "") or "")
    status = 400 if code.startswith("23") else 502
    raise HTTPException(
        status_code=status,
        detail=f"Database rejected the write: {detail}",
    )

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
