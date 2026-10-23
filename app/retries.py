"""PostgreSQL retry policy with idempotency-aware replay and jittered backoff."""

import logging
import random
import time

import psycopg
from psycopg_pool import PoolTimeout

from app import config as app_config

log = logging.getLogger("hrdesk.retries")

READ = "read"
WRITE = "write"
GUARDED = "guarded"

_RETRYABLE_EXACT = {"40001", "40P01"}
_RETRYABLE_CLASSES = ("53", "54", "57", "58")


def backoff_delay(attempt: int, *, initial: float, cap: float, rnd=random) -> float:
    """Full-jitter exponential backoff for attempt n (1-based), bounded."""
    if initial <= 0:
        return 0.0
    raw = initial * (2 ** (max(0, attempt - 1)))
    return rnd.uniform(0.0, min(cap if cap > 0 else raw, raw))


def _transient(e: BaseException, mode: str) -> bool:
    """Return whether a PostgreSQL failure is safe to replay for this query."""
    if isinstance(e, PoolTimeout):
        return True

    state = getattr(e, "sqlstate", None) or ""
    if state == "57014" or state.startswith(("22", "23", "28", "42")):
        return False
    retryable_state = state in _RETRYABLE_EXACT or state.startswith(_RETRYABLE_CLASSES)
    if retryable_state:
        return True

    if mode == GUARDED:
        return False
    return isinstance(e, (psycopg.OperationalError, psycopg.InterfaceError))


def retry_call(op, *, mode: str = READ, attempts: int | None = None):
    """Run op() applying this module's retry policy.

    Failures either retry (sleep between tries with full jitter) or re-raise
    the ORIGINAL exception — callers keep their existing error mapping. The
    config values are read at call time so tests can retune them freely.
    """
    max_attempts = max(1, attempts if attempts is not None else app_config.RETRY_MAX_ATTEMPTS)
    for n in range(1, max_attempts + 1):
        try:
            return op()
        except Exception as e:
            if n >= max_attempts or not _transient(e, mode):
                raise
            delay = backoff_delay(
                n,
                initial=app_config.RETRY_BACKOFF_INITIAL_S,
                cap=app_config.RETRY_BACKOFF_MAX_S,
            )
            log.warning(
                "Transient %s failure (attempt %d/%d, %s%s) — retrying in %.2fs",
                mode,
                n,
                max_attempts,
                type(e).__name__,
                f", SQLSTATE={e.sqlstate}" if isinstance(e, psycopg.Error) and e.sqlstate else "",
                delay,
            )
            if delay > 0:
                time.sleep(delay)


def classify_mode(statement: str) -> str:
    """Classify a PostgreSQL statement; unknown or compound SQL is guarded."""
    operation = statement.lstrip().split(None, 1)[0].lower() if statement.strip() else ""
    if operation == "select":
        return READ
    if operation in {"update", "delete"}:
        return WRITE
    return GUARDED
