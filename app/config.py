"""Central configuration + Supabase client singleton.

This module is the ONLY place that resolves environment values and builds
the shared Supabase client. Repositories receive that client via
app/deps.py; nothing else imports it directly.

(The old `db()` shortcut for the tickets table no longer exists — the ticket
repository always builds a fresh `client.table("tickets")` chain itself.)
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

# backend/.env lives next to the app/ package's parent
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
CORS_ORIGINS = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
]
SIGNED_URL_TTL = int(os.getenv("ATTACHMENT_SIGNED_URL_TTL", "3600"))

# Circuit breakers (app/resilience.py): after this many consecutive classified
# failures on one Supabase surface, calls to it fail fast for the cooldown.
BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
BREAKER_RECOVERY_SECONDS = float(os.getenv("CIRCUIT_BREAKER_RECOVERY_SECONDS", "30"))

# -- timeouts (the general norm: budget every outbound call) ------------------
# Every outbound Supabase call (PostgREST tables + Storage) runs under this
# budget, seconds. The library default is a flat 120 s, which is far too
# permissive: a stalled connection would pin a worker for two minutes instead
# of failing fast. Norm: a generous overall window (remote-region round trips
# on home networks are real) but a snap-quick connect failure — a dead host
# is known within seconds, and the retry layer (app/retries.py) then acts on it.
SUPABASE_TIMEOUT = float(os.getenv("SUPABASE_TIMEOUT", "60"))
CONNECT_TIMEOUT = float(os.getenv("SUPABASE_CONNECT_TIMEOUT", "10"))

# -- retries (app/retries.py: retry only what is safe to repeat) --------------
# Applied at the repository boundary:
#   reads  -> full retry (transient 5xx/429, read timeouts, connect failures)
#   writes -> connect-phase failures only: the request provably never reached
#             the server, so a retry can never duplicate a ticket.
RETRY_MAX_ATTEMPTS = max(1, int(os.getenv("RETRY_MAX_ATTEMPTS", "3")))
RETRY_BACKOFF_INITIAL_S = max(0.0, float(os.getenv("RETRY_BACKOFF_INITIAL_S", "0.5")))
RETRY_BACKOFF_MAX_S = max(0.0, float(os.getenv("RETRY_BACKOFF_MAX_S", "2.0")))

# Must match the buckets created by schema.sql
ATTACHMENT_BUCKET = "ticket-attachments"
KB_BUCKET = "knowledge-base"
# 5 MB cap, mirrors the frontend TicketForm limit
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

# --- observability (logging + tracing; see README §11) ----------------------
# floor level for app logs: debug | info | warning | error
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
# console (human) | json (one JSON object per line)
LOG_FORMAT = os.getenv("LOG_FORMAT", "console").strip().lower()
# false removes ALL tracing instrumentation and export (zero overhead)
TRACE_ENABLED = os.getenv("TRACE_ENABLED", "true").strip().lower() not in (
    "false", "0", "no", "off"
)
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "hrdesk-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318"
)
# --- persistent log files ---------------------------------------------------
# daily-rotating JSON log file (see README §11: location + retention)
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").strip().lower() not in (
    "false", "0", "no", "off"
)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH") or str(BASE_DIR / "logs" / "app.log")
LOG_FILE_RETENTION_DAYS = int(os.getenv("LOG_FILE_RETENTION_DAYS", "14"))

_client: Optional[Client] = None

# (module, attribute) candidates for the options class create_client wants,
# best first: supabase._sync.client's ClientOptions IS create_client's own
# alias on every 2.x line, so in practice the first probe wins.
_OPTION_SOURCE_CANDIDATES = (
    ("supabase._sync.client", "ClientOptions"),
    ("supabase._async.client", "ClientOptions"),
    ("supabase.lib.client_options", "SyncClientOptions"),
    ("supabase.lib.client_options", "ClientOptions"),
    ("supabase.client", "ClientOptions"),
    ("supabase", "ClientOptions"),
)


def _build_options(candidates=None):
    """ClientOptions with explicit timeouts, version-tolerant.

    supabase-py's options class has drifted across releases: current 2.x
    ships SyncClientOptions — ClientOptions in supabase.lib.client_options
    is its base WITHOUT the .storage attribute (create_client crashes on
    `client_options.storage` if it is handed the base), while older lines
    exposed ClientOptions under other module paths. The construction that
    is safe everywhere:

      1. resolve the SAME class create_client itself imports (candidates
         above, injectable for tests);
      2. default-CONSTRUCT it — a no-arg build always yields the complete
         field set (headers, storage, auto_refresh_token, ...), never a
         half-shaped object;
      3. assign only the two timeout attributes we manage, guarded by
         hasattr, so unknown future fields simply keep their defaults.

    Returns None when nothing matches; get_client() then builds the client
    without options — library default timeouts — instead of failing startup.
    """
    try:
        import httpx

        bounded = httpx.Timeout(
            SUPABASE_TIMEOUT,
            connect=min(CONNECT_TIMEOUT, SUPABASE_TIMEOUT),
        )
    except Exception:  # pragma: no cover - httpx ships with supabase
        bounded = SUPABASE_TIMEOUT

    for mod, attr in (candidates or _OPTION_SOURCE_CANDIDATES):
        try:
            module = __import__(mod, fromlist=[attr])
            cls = getattr(module, attr, None)
            if cls is None:
                continue
            options = cls()  # complete default shape; .storage present on sync-era classes
            if not hasattr(options, "postgrest_client_timeout"):
                continue
            options.postgrest_client_timeout = bounded
            if hasattr(options, "storage_client_timeout"):
                options.storage_client_timeout = max(int(SUPABASE_TIMEOUT), 40)
            return options
        except (ImportError, AttributeError, TypeError):
            continue
    return None


def get_client() -> Client:
    """Lazy Supabase singleton (service role key = bypasses RLS, server-side
    only), built with the explicit timeout budgets above."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SERVICE_KEY:
            raise RuntimeError(
                "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. "
                "Copy backend/.env.example to backend/.env and fill in the values."
            )
        options = _build_options()
        _client = (
            create_client(SUPABASE_URL, SERVICE_KEY, options)
            if options is not None
            else create_client(SUPABASE_URL, SERVICE_KEY)
        )
    return _client
