"""Central configuration and PostgreSQL connection-pool singleton."""

import os
import threading
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
ATTACHMENT_SIGNING_KEY = os.getenv("ATTACHMENT_SIGNING_KEY", "")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
SIGNED_URL_TTL = int(os.getenv("ATTACHMENT_SIGNED_URL_TTL", "3600"))
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))
DB_POOL_TIMEOUT = float(os.getenv("DB_POOL_TIMEOUT", "5"))
RETRY_MAX_ATTEMPTS = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
RETRY_BACKOFF_INITIAL_S = float(os.getenv("RETRY_BACKOFF_INITIAL_S", "0.5"))
RETRY_BACKOFF_MAX_S = float(os.getenv("RETRY_BACKOFF_MAX_S", "2"))

BREAKER_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
BREAKER_RECOVERY_SECONDS = float(os.getenv("CIRCUIT_BREAKER_RECOVERY_SECONDS", "30"))

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024

LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
LOG_FORMAT = os.getenv("LOG_FORMAT", "console").strip().lower()
TRACE_ENABLED = os.getenv("TRACE_ENABLED", "true").strip().lower() not in (
    "false",
    "0",
    "no",
    "off",
)
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "hrdesk-api")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS = int(os.getenv("OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS", "300"))
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").strip().lower() not in ("false", "0", "no", "off")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH") or str(BASE_DIR / "logs" / "app.log")
LOG_FILE_RETENTION_DAYS = int(os.getenv("LOG_FILE_RETENTION_DAYS", "14"))

_database: Optional[ConnectionPool] = None
_database_lock = threading.Lock()


def get_database() -> ConnectionPool:
    """Return the lazily-created shared PostgreSQL pool."""
    global _database
    if _database is None:
        with _database_lock:
            if _database is None:
                if not DATABASE_URL:
                    raise RuntimeError(
                        "Missing DATABASE_URL. Copy .env.example to .env and configure PostgreSQL."
                    )
                if DB_POOL_MIN_SIZE < 0 or DB_POOL_MAX_SIZE < 1:
                    raise RuntimeError("DB_POOL_MIN_SIZE and DB_POOL_MAX_SIZE are invalid.")
                if DB_POOL_MIN_SIZE > DB_POOL_MAX_SIZE:
                    raise RuntimeError("DB_POOL_MIN_SIZE cannot exceed DB_POOL_MAX_SIZE.")
                _database = ConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=DB_POOL_MIN_SIZE,
                    max_size=DB_POOL_MAX_SIZE,
                    timeout=DB_POOL_TIMEOUT,
                    kwargs={"row_factory": dict_row},
                    open=False,
                )
                _database.open(wait=False)
    return _database


def close_database() -> None:
    """Close the shared pool during application shutdown."""
    global _database
    with _database_lock:
        if _database is not None:
            _database.close()
            _database = None
