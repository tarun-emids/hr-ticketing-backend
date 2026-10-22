"""Resilience policy: mode classification, transient detection, backoff.

These tests pin the contract of app/retries.py:
  - reads/update-delete fully retry transient failures; inserts retry ONLY
    on connect-phase failures (the request provably never left the client);
  - constraint violations / client errors NEVER retry;
  - backoff is full-jitter exponential bounded by the configured envelope.
    (time.sleep is monkeypatched — tests never actually wait.)
"""
import random

import httpx
import pytest
from postgrest.exceptions import APIError

from app.retries import (
    GUARDED,
    READ,
    WRITE,
    backoff_delay,
    classify_mode,
    retry_call,
)


def _apierr(code: str) -> APIError:
    return APIError({"message": "boom", "code": code})


class _Sleeper:
    """Replaces retries.time.sleep; records delays instead of waiting."""

    def __init__(self, monkeypatch):
        self.calls = []
        monkeypatch.setattr("app.retries.time.sleep", self.calls.append)


@pytest.fixture()
def sleeper(monkeypatch):
    return _Sleeper(monkeypatch)


def _retries_for(err, mode: str, attempts: int = 3) -> int:
    """How many retries a perpetually-failing op receives under `mode`."""
    tries = {"n": 0}

    def op():
        tries["n"] += 1
        raise err

    with pytest.raises(type(err)):
        retry_call(op, mode=mode, attempts=attempts)
    return tries["n"] - 1  # one try is not a retry


# -- mode classification ---------------------------------------------------

def _builder_like(class_name: str):
    """Instance of a builder whose terminal type carries `class_name` —
    classify_mode inspects type(instance).__name__, exactly like real
    postgrest-py query builders do."""
    return type(class_name, (), {})()


def test_select_builders_are_reads():
    assert classify_mode(_builder_like("SyncSelectRequestBuilder")) == READ


def test_update_delete_builders_are_writes():
    assert classify_mode(_builder_like("SyncFilterRequestBuilder")) == WRITE


def test_insert_upsert_rpc_builders_are_guarded():
    assert classify_mode(_builder_like("SyncQueryRequestBuilder")) == GUARDED
    assert classify_mode(_builder_like("SyncSingleRequestBuilder")) == GUARDED


def test_unknown_builder_degrades_to_guarded():
    # Safe default for anything unrecognised: assume it may write.
    assert classify_mode(_builder_like("FutureBuilder")) == GUARDED
    assert classify_mode(_builder_like("FakeQueryBuilder")) == GUARDED


# -- transient semantics -----------------------------------------------------

def test_connect_failures_are_transient_in_every_mode():
    err = httpx.ConnectError("refused")
    for mode in (READ, WRITE, GUARDED):
        assert _retries_for(err, mode) > 0, f"{mode} should replay a never-sent request"


def test_read_timeout_retries_reads_and_writes_but_not_inserts():
    err = httpx.ReadTimeout("slow upstream")
    assert _retries_for(err, READ) > 0
    # updates/deletes replay the same patch -> same end state
    assert _retries_for(err, WRITE) > 0
    # inserts must never replay an ambiguous timeout
    assert _retries_for(err, GUARDED) == 0


def test_postgres_transient_codes_retry_for_read_mode():
    for code in ("429", "53300", "57P01", "40001", "40P01"):
        assert _retries_for(_apierr(code), READ) > 0, code


def test_postgres_client_error_codes_never_retry():
    for code in ("23503", "42P01", "42501", "PGRST201"):
        assert _retries_for(_apierr(code), READ) == 0, code


def test_guarded_mode_only_replays_connect_phase():
    assert _retries_for(_apierr("53300"), GUARDED) == 0
    assert _retries_for(_apierr("429"), GUARDED) == 0
    assert _retries_for(httpx.ConnectError("refused"), GUARDED) > 0


# -- exhaustion + non-transient ------------------------------------------------

def test_exhausted_retries_reraise_original_exception(sleeper):
    sentinel = httpx.ConnectError("never up")
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise sentinel

    with pytest.raises(httpx.ConnectError) as excinfo:
        retry_call(op, mode=READ, attempts=3)
    assert excinfo.value is sentinel
    assert calls["n"] == 3
    assert len(sleeper.calls) == 2  # sleep between tries, never after the last


def test_non_transient_errors_fail_immediately(sleeper):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise ValueError("bad request shape")

    with pytest.raises(ValueError):
        retry_call(op, mode=READ, attempts=3)
    assert calls["n"] == 1 and sleeper.calls == []


def test_attempts_override_is_honoured(sleeper):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        retry_call(op, mode=READ, attempts=5)
    assert calls["n"] == 5


def test_single_attempt_never_retries_nor_sleeps(sleeper):
    calls = {"n": 0}

    def op():
        calls["n"] += 1
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        retry_call(op, mode=READ, attempts=1)
    assert calls["n"] == 1 and sleeper.calls == []


# -- backoff shape ---------------------------------------------------------

def test_backoff_is_bounded_by_the_cap():
    for attempt in range(1, 6):
        d = backoff_delay(attempt, initial=0.5, cap=2.0, rnd=random)
        assert 0.0 <= d <= 2.0


def test_backoff_envelope_doubles_until_capped():
    class _CeilingRnd:
        def uniform(self, low: float, high: float) -> float:
            return high

    sequence = [
        backoff_delay(attempt, initial=0.25, cap=0.75, rnd=_CeilingRnd())
        for attempt in range(1, 5)
    ]
    # 0.25 -> 0.5 -> 1.0(capped 0.75 from here on)
    assert sequence[0] == 0.25
    assert sequence[1] == 0.5
    assert sequence[2] == sequence[3] == 0.75


def test_backoff_zero_initial_never_sleeps():
    assert backoff_delay(3, initial=0.0, cap=2.0) == 0.0
