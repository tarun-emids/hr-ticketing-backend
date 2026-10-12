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

# Must match the bucket created by schema.sql
ATTACHMENT_BUCKET = "ticket-attachments"
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
# Collapse repeated OTLP exporter failure logs to at most one raw line per
# window (seconds) plus a backend summary. 0/negative disables the throttle.
OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS = int(
    os.getenv("OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS", "300")
)
# --- persistent log files ---------------------------------------------------
# daily-rotating JSON log file (see README §11: location + retention)
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").strip().lower() not in (
    "false", "0", "no", "off"
)
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH") or str(BASE_DIR / "logs" / "app.log")
LOG_FILE_RETENTION_DAYS = int(os.getenv("LOG_FILE_RETENTION_DAYS", "14"))

_client: Optional[Client] = None


def get_client() -> Client:
    """Lazy Supabase singleton (service role key = bypasses RLS, server-side only)."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SERVICE_KEY:
            raise RuntimeError(
                "Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY. "
                "Copy backend/.env.example to backend/.env and fill in the values."
            )
        _client = create_client(SUPABASE_URL, SERVICE_KEY)
    return _client
