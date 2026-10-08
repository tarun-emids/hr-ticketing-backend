"""Circuit breakers for the three Supabase network surfaces.

Supabase is this app's only external dependency, reached over the network in
three independent places:

    db_breaker      PostgREST — every repository call funnels through
                    run()/rows_of()/first_of() in app/repositories/base.py
    auth_breaker    GoTrue password grant — app/services/auth_service._grant()
    storage_breaker Storage bucket ops — app/repositories/attachment_storage.py

When a surface is failing (outage, overload, stalled network), the breaker
flips to OPEN and callers get an immediate 503 instead of paying a full
network round trip — and the struggling dependency stops being hammered,
so it can recover. One half-open probe is admitted after the cooldown;
if it succeeds the circuit closes again.

WHY hand-rolled instead of a library: the failure classification is not
exception-type-based. PostgREST FK violations (code 23xxx) and GoTrue
401/422 responses mean the DEPENDENCY IS HEALTHY — the caller is wrong — and
must not trip the breaker. That "neutral outcome" concept needs a predicate
call sites control per call (`is_failure=`), which is exactly one parameter
here. Deps: stdlib only.

The module deliberately has no FastAPI import: `CircuitOpenError` is
translated to HTTPException(503) NEXT TO the raise site, where the
per-surface detail message lives (the generic exception handler in
app/main.py must never see it).

Env knobs (read in app/config.py): CIRCUIT_BREAKER_FAILURE_THRESHOLD
(default 5 consecutive failures), CIRCUIT_BREAKER_RECOVERY_SECONDS
(default 30 s cooldown before the half-open probe).
"""
import logging
import threading
import time
from typing import Any, Callable, Optional

from app import config as app_config

log = logging.getLogger("hrdesk.resilience")

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """The circuit for a dependency is open — fails fast instead of hanging.

    Call sites translate this to their own HTTPException(503, ...) so each
    surface can word the user-facing message (db/auth/storage).
    """

    def __init__(self, name: str):
        super().__init__(f"Dependency '{name}' is temporarily unavailable")
        self.name = name


class CircuitBreaker:
    """Thread-safe closed/open/half-open breaker around zero-arg callables.

    Endpoints run in the FastAPI threadpool (and the background sweep in a
    thread), so state transitions — never the guarded call itself — happen
    under one lock. Outcomes:

    - success             -> consecutive-failure counter resets to 0
    - is_failure(e)=True  -> counter +1; at the threshold the breaker opens
    - is_failure(e)=False -> NEUTRAL (caller error; counter untouched) —
                             except on the half-open probe, where it PROVES
                             the dependency is reachable and closes the circuit
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        is_failure: Optional[Callable[[BaseException], bool]] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._is_failure = is_failure or (lambda exc: True)
        self._lock = threading.Lock()
        self._state = CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    # -- guarded execution ---------------------------------------------------

    def call(
        self,
        fn: Callable[[], Any],
        *,
        is_failure: Optional[Callable[[BaseException], bool]] = None,
    ) -> Any:
        """Run fn() once behind the breaker, or raise CircuitOpenError without
        calling it. is_failure overrides the constructor predicate per call."""
        classify = is_failure or self._is_failure
        self._admit()
        try:
            result = fn()
        except Exception as exc:  # neutral/failure classified inside; always re-raised
            self._record(exc, classify)
            raise
        self._succeeded()
        return result

    # -- state transitions (all under self._lock) ----------------------------

    def _admit(self) -> None:
        with self._lock:
            if self._state == CLOSED:
                return
            now = time.monotonic()
            if self._state == OPEN:
                if now - self._opened_at < self.recovery_timeout:
                    raise CircuitOpenError(self.name)
                self._state = HALF_OPEN
                log.info("circuit '%s' HALF_OPEN — probing with one request", self.name)
            # HALF_OPEN: exactly one probe; everyone else fails fast
            if self._probe_in_flight:
                raise CircuitOpenError(self.name)
            self._probe_in_flight = True

    def _record(self, exc: Exception, classify: Callable[[BaseException], bool]) -> None:
        with self._lock:
            failure = classify(exc)
            if self._state == CLOSED:
                if not failure:
                    return  # caller error says nothing about dependency health
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._open_locked(exc)
            else:  # this thread ran the half-open probe; its outcome decides
                self._probe_in_flight = False
                if failure:
                    self._open_locked(exc, recovered_probe=False)
                else:
                    # a caller error still proves the dependency answers
                    self._close_locked()

    def _succeeded(self) -> None:
        with self._lock:
            self._failures = 0
            self._probe_in_flight = False
            if self._state != CLOSED:
                self._close_locked()

    def _open_locked(self, exc: Exception, *, recovered_probe: bool = True) -> None:
        self._state = OPEN
        self._opened_at = time.monotonic()
        self._probe_in_flight = False
        verb = "re-opened (probe failed)" if not recovered_probe else "open"
        log.warning(
            "circuit '%s' %s after %d consecutive failures (last: %s: %s) "
            "— callers get an immediate 503 for %.0fs",
            self.name, verb, self._failures, type(exc).__name__, exc,
            self.recovery_timeout,
        )
        self._failures = self.failure_threshold  # counter freezes while open

    def _close_locked(self) -> None:
        self._state = CLOSED
        self._failures = 0
        self._probe_in_flight = False
        log.info("circuit '%s' CLOSED — dependency recovered", self.name)

    # -- introspection ---------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            out = {"name": self.name, "state": self._state, "failures": self._failures}
            if self._state == OPEN:
                remaining = self.recovery_timeout - (time.monotonic() - self._opened_at)
                out["secondsUntilProbe"] = max(0.0, round(remaining, 1))
            return out

    def reset(self) -> None:
        """Back to closed/counters-zero (tests + manual ops recovery)."""
        with self._lock:
            self._close_locked()


db_breaker = CircuitBreaker("db",
                            failure_threshold=app_config.BREAKER_FAILURE_THRESHOLD,
                            recovery_timeout=app_config.BREAKER_RECOVERY_SECONDS)
auth_breaker = CircuitBreaker("auth",
                              failure_threshold=app_config.BREAKER_FAILURE_THRESHOLD,
                              recovery_timeout=app_config.BREAKER_RECOVERY_SECONDS)
storage_breaker = CircuitBreaker("storage",
                                 failure_threshold=app_config.BREAKER_FAILURE_THRESHOLD,
                                 recovery_timeout=app_config.BREAKER_RECOVERY_SECONDS)


def breakers_snapshot() -> dict:
    """{name: snapshot} for the GET /health/deps endpoint, in a stable order."""
    return {b.name: b.snapshot() for b in (db_breaker, auth_breaker, storage_breaker)}
