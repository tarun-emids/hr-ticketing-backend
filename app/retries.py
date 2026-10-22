"""Shared timeout + retry policy for every outbound call (the general norm).

One module defines what "transient" means and one algorithm defines the wait:

Mode classification (by terminal PostgREST builder type — see classify_mode):
    "read"    select chains. Fully retryable: a repeat can never change data.
    "write"   update/delete chains (idempotent — replaying the same patch or
              delete predicate reaches the same state).
    "guarded" insert/upsert/rpc (NOT idempotent: a replayed ticket insert
              could duplicate a row).

Policy per mode:
    read / write -> retry on transient response codes 5xx-class Postgres
                    errors + 429 + read/connect timeouts + connect reset.
    guarded      -> retry ONLY when the request provably never reached the
                    server (connect-phase failures). A 502 that arrives after
                    the row may already be committed must NOT be replayed;
                    retries are a resilience net here, not a correctness tool.

Transient code classes (SQLSTATE): 53xxx insufficient resources (too many
connections), 54xxx/57xxx operator intervention (crash recovery, admin
shutdown), 58xxx system I/O, 40001 serialization failure, 40P01 deadlock —
all safe to replay. Constraint (23xxx) / SQL misuse (42xxx) / RLS denials
fail through to the API's 4xx mapping immediately.

Backoff: full-jitter exponential — uniform(0, min(cap, initial * 2^(n-1)))
per AWS Builders' Library guidance — capped per attempt, attempts capped.
All knobs live in app.config so the policy is env-tunable without a deploy.

COMPOSING WITH CIRCUIT BREAKERS (app/resilience.py): breakers and retries
answer different failures — breakers fail fast once a dependency is provably
down, retries smooth over isolated blips. Call sites therefore put the
breaker INSIDE the retry loop:

    retry_call(lambda: db_breaker.call(op), mode=...)

Each attempt is admitted by the breaker, so while a circuit is OPEN the
CircuitOpenError is not transient (see _transient — it is no APIError /
httpx error) and no point is wasted retrying it.
"""
import logging
import random
import time

import httpx
from postgrest.exceptions import APIError

from app import config as app_config

log = logging.getLogger("hrdesk.retries")

READ = "read"
WRITE = "write"
GUARDED = "guarded"

# SQLSTATE classes/values that mean "the database flaked, not your query".
_RETRYABLE_EXACT = {"429", "40001", "40P01", "XX000"}
_RETRYABLE_CLASSES = ("53", "54", "57", "58")


def backoff_delay(attempt: int, *, initial: float, cap: float, rnd=random) -> float:
    """Full-jitter exponential backoff for attempt n (1-based), bounded."""
    if initial <= 0:
        return 0.0
    raw = initial * (2 ** (max(0, attempt - 1)))
    return rnd.uniform(0.0, min(cap if cap > 0 else raw, raw))


def _is_connect_phase_failure(e: BaseException) -> bool:
    """The TCP connection was never established — no request was sent, so the
    server cannot have applied anything. httpx.ConnectTimeout subclasses
    ConnectError, so one isinstance covers both."""
    return isinstance(e, httpx.ConnectError)


def _is_read_timeout(e: BaseException) -> bool:
    """The request went out but no (complete) answer ever came back. Only
    replayable for reads — for a write, 'no answer' means 'may have applied'."""
    return isinstance(e, (httpx.ReadTimeout, httpx.RemoteProtocolError))


def _apierror_retryable(e: APIError) -> bool:
    code = str(getattr(e, "code", "") or "")
    if code in _RETRYABLE_EXACT:
        return True
    return code[:2] in _RETRYABLE_CLASSES


def _transient(e: BaseException, mode: str) -> bool:
    """Should op() be replayed after this failure, given the idempotency mode?

    CircuitOpenError falls through as False on every branch: an open circuit
    is a fail-fast signal, not a blip to ride out.
    """
    if _is_connect_phase_failure(e):
        return True  # every mode: nothing was ever sent
    if mode == GUARDED:
        return False  # anything else on an insert: must not replay
    if isinstance(e, APIError):
        return _apierror_retryable(e)
    return _is_read_timeout(e)


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
                f", code={getattr(e, 'code', None)}" if isinstance(e, APIError) else "",
                delay,
            )
            if delay > 0:
                time.sleep(delay)


def classify_mode(builder) -> str:
    """read / write / guarded from the terminal PostgREST builder type.

    postgrest-py's chain terminals (name stable across the 0.x and 2.x line
    generations): select chains end in *Select*RequestBuilder; update/delete
    end in *Filter*RequestBuilder; insert/upsert end in *Query*RequestBuilder
    and rpc in *Single*RequestBuilder. Anything unrecognised degrades to
    guarded — the safest assumption for an unknown builder is 'may write'.
    The offline test fake returns a plain FakeQueryBuilder: never retryable,
    which tests exercise explicitly, not implicitly.
    """
    name = type(builder).__name__.lower()
    if "select" in name:
        return READ
    if "filter" in name:
        return WRITE
    return GUARDED
