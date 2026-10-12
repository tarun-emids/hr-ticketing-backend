"""Circuit breaker state machine — offline, no Supabase, no threads except
where a half-open probe must genuinely be in flight to prove stampede-guard."""

import concurrent.futures
import threading

import pytest

from app.resilience import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    CircuitBreaker,
    CircuitOpenError,
)


def always_down(exc) -> bool:
    return True


def test_opens_after_threshold_consecutive_failures():
    brk = CircuitBreaker("t", failure_threshold=3, recovery_timeout=60.0)

    for _ in range(3):
        with pytest.raises(RuntimeError, match="down"):
            brk.call(lambda: (_ for _ in ()).throw(RuntimeError("down")), is_failure=always_down)

    snap = brk.snapshot()
    assert snap["state"] == OPEN
    assert snap["failures"] == 3
    assert 0 < snap["secondsUntilProbe"] <= 60


def test_neutral_outcome_never_counts():
    brk = CircuitBreaker("t", failure_threshold=2, recovery_timeout=60.0)

    def user_error():
        raise ValueError("bad request")  # e.g. PostgREST 23xxx / GoTrue 401

    for _ in range(10):
        with pytest.raises(ValueError):
            brk.call(user_error, is_failure=lambda exc: False)

    assert brk.snapshot() == {"name": "t", "state": CLOSED, "failures": 0}


def test_success_resets_failure_counter():
    brk = CircuitBreaker("t", failure_threshold=3, recovery_timeout=60.0)
    raise_exc = lambda: (_ for _ in ()).throw(RuntimeError("down"))

    for _ in range(2):
        with pytest.raises(RuntimeError):
            brk.call(raise_exc, is_failure=always_down)

    assert brk.call(lambda: "ok", is_failure=always_down) == "ok"

    for _ in range(2):
        with pytest.raises(RuntimeError):
            brk.call(raise_exc, is_failure=always_down)

    # only 2 consecutive since the last success — still closed
    assert brk.snapshot()["state"] == CLOSED

    with pytest.raises(RuntimeError):
        brk.call(raise_exc, is_failure=always_down)
    assert brk.snapshot()["state"] == OPEN


def test_open_circuit_fails_fast_without_calling_the_dependency():
    brk = CircuitBreaker("t", failure_threshold=1, recovery_timeout=60.0)
    with pytest.raises(RuntimeError):
        brk.call(lambda: (_ for _ in ()).throw(RuntimeError("down")), is_failure=always_down)

    called = []

    with pytest.raises(CircuitOpenError, match="temporarily unavailable"):
        brk.call(lambda: called.append(1))

    assert called == []  # OPEN never touches the dependency


def test_only_one_half_open_probe_is_admitted():
    """Concurrent callers during an unresolved probe must not stampede — the
    second request gets a fast CircuitOpenError while the probe is running.
    Zero cooldown so the very next call is admitted as the probe."""
    brk = CircuitBreaker("t", failure_threshold=1, recovery_timeout=0.0)
    with pytest.raises(RuntimeError):
        brk.call(lambda: (_ for _ in ()).throw(RuntimeError("down")), is_failure=always_down)

    started = threading.Event()
    release = threading.Event()

    def probe():
        started.set()
        release.wait(2.0)
        return "recovered"

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(brk.call, probe)
        assert started.wait(2.0)  # probe is admitted and inside fn()

        assert brk.snapshot()["state"] == HALF_OPEN
        with pytest.raises(CircuitOpenError):
            brk.call(lambda: "rejected second request")

        release.set()
        assert fut.result() == "recovered"

    snap = brk.snapshot()
    assert snap["state"] == CLOSED
    assert snap["failures"] == 0


def test_failed_half_open_probe_reopens():
    brk = CircuitBreaker("t", failure_threshold=1, recovery_timeout=0.0)
    with pytest.raises(RuntimeError):
        brk.call(lambda: (_ for _ in ()).throw(RuntimeError("down")), is_failure=always_down)

    # zero cooldown: the next call IS the probe, and it fails again
    with pytest.raises(RuntimeError, match="still down"):
        brk.call(lambda: (_ for _ in ()).throw(RuntimeError("still down")), is_failure=always_down)

    assert brk.snapshot()["state"] == OPEN


def test_probe_outcome_with_caller_error_closes_the_circuit():
    """A probe that gets an ANSWER — even a caller error (23xxx / 401 shape) —
    proves the dependency is reachable and closes the circuit."""
    brk = CircuitBreaker("auth", failure_threshold=2, recovery_timeout=0.0)

    def outage():
        raise ConnectionError("no route to auth service")

    for _ in range(2):
        with pytest.raises(ConnectionError):
            brk.call(outage, is_failure=lambda exc: True)

    assert brk.snapshot()["state"] == OPEN

    def answered_with_caller_error():
        raise ValueError("bad credentials")  # GoTrue answered 401

    # neutral predicate: probe resolves to a caller error, still evidence of life
    with pytest.raises(ValueError):
        brk.call(answered_with_caller_error, is_failure=lambda exc: False)

    snap = brk.snapshot()
    assert snap["state"] == CLOSED
    assert snap["failures"] == 0


def test_reset_reopens_business_as_usual():
    brk = CircuitBreaker("t", failure_threshold=1, recovery_timeout=60.0)
    with pytest.raises(RuntimeError):
        brk.call(lambda: (_ for _ in ()).throw(RuntimeError("down")), is_failure=always_down)
    assert brk.snapshot()["state"] == OPEN

    brk.reset()
    assert brk.snapshot() == {"name": "t", "state": CLOSED, "failures": 0}
    assert brk.call(lambda: "ok") == "ok"


# ---------------------------------------------------------------------------
# run() integration: real module-level db breaker + the PostgREST error classes
# it must distinguish (constraint violations are caller errors, never outages)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_db_breaker():
    from app.repositories import base as repositories_base

    repositories_base.db_breaker.reset()
    yield
    repositories_base.db_breaker.reset()


def _query(raiser):
    class _Q:
        def execute(self):
            raiser()

    return _Q()


def test_postgrest_constraint_violation_is_neutral_and_maps_400():
    from fastapi import HTTPException
    from postgrest.exceptions import APIError

    from app.repositories import base as repositories_base

    fk = lambda: (_ for _ in ()).throw(  # noqa: E731
        APIError({"message": "insert violates foreign key", "code": "23503"})
    )
    for _ in range(50):  # far beyond any threshold — these must never trip it
        with pytest.raises(HTTPException) as ei:
            repositories_base.run(_query(fk))
        assert ei.value.status_code == 400
        assert "Database rejected the write" in ei.value.detail

    snap = repositories_base.db_breaker.snapshot()
    assert snap["state"] == CLOSED
    assert snap["failures"] == 0


def test_postgrest_non_constraint_error_counts_and_maps_502():
    from fastapi import HTTPException
    from postgrest.exceptions import APIError

    from app.repositories import base as repositories_base

    disaster = lambda: (_ for _ in ()).throw(  # noqa: E731
        APIError({"message": "connection terminated", "code": "57P01"})
    )
    with pytest.raises(HTTPException) as ei:
        repositories_base.run(_query(disaster))
    assert ei.value.status_code == 502
    assert repositories_base.db_breaker.snapshot()["failures"] == 1


def test_transport_failure_through_run_counts():
    from app.repositories import base as repositories_base

    dead = lambda: (_ for _ in ()).throw(RuntimeError("read timeout"))  # noqa: E731
    with pytest.raises(RuntimeError, match="read timeout"):  # unmapped: 500 handler today
        repositories_base.run(_query(dead))
    assert repositories_base.db_breaker.snapshot()["failures"] == 1
