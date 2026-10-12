"""Auth breaker classification + login-flow wiring.

Offline: supabase.create_client is monkeypatched (auth_service._grant imports
it at call time), so the GoTrue password grant never touches the network.
The auth breaker is reset before/after every test."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.resilience import CircuitBreaker, CLOSED, OPEN
from app.services import auth_service as asvc


class _AuthApiErrorStub(Exception):
    """Everything `_is_grant_error` duck-types: class name containing
    'AuthApiError' plus .message/.status like every supabase-py generation."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.message = message
        self.status = status


def _stub_grant(monkeypatch, raises):
    """Replace supabase.create_client() with a client whose
    auth.sign_in_with_password always raises `raises()`."""
    import supabase

    def fake_create_client(url, key):
        def sign_in(creds):
            raise raises()

        return SimpleNamespace(auth=SimpleNamespace(sign_in_with_password=sign_in))

    monkeypatch.setattr(supabase, "create_client", fake_create_client)


def _auth_service():
    # The user store is irrelevant for grant-error paths: login either returns
    # after resolution or raises from _grant — never reaches account lookup.
    return asvc.AuthService(SimpleNamespace())


@pytest.fixture(autouse=True)
def _fresh_auth_breaker():
    asvc.auth_breaker.reset()
    yield
    asvc.auth_breaker.reset()


def test_classification_counts_outages_but_not_answered_grants():
    assert asvc._auth_failure(_AuthApiErrorStub("invalid login credentials", 401)) is False
    assert asvc._auth_failure(_AuthApiErrorStub("could not identify client", 422)) is False
    assert asvc._auth_failure(_AuthApiErrorStub("auth service overloaded", 503)) is True
    assert asvc._auth_failure(RuntimeError("connection refused")) is True


def test_transport_failures_trip_and_login_then_fails_fast_503(monkeypatch):
    _stub_grant(monkeypatch, lambda: RuntimeError("connection refused"))
    monkeypatch.setattr(
        asvc,
        "auth_breaker",
        CircuitBreaker("auth", failure_threshold=2, recovery_timeout=60.0),
    )
    svc = _auth_service()

    for _ in range(2):
        with pytest.raises(HTTPException) as ei:
            svc.login("ada@acme.com", "pw")
        assert ei.value.status_code == 502
        assert "Could not reach the authentication service" in ei.value.detail

    # breaker open while it was tripping: the third login gets 503 instantly
    with pytest.raises(HTTPException) as ei:
        svc.login("ada@acme.com", "pw")
    assert ei.value.status_code == 503
    assert "temporarily unavailable" in ei.value.detail

    assert asvc.auth_breaker.snapshot()["state"] == OPEN


def test_answered_bad_credentials_never_trip_the_breaker(monkeypatch):
    _stub_grant(
        monkeypatch,
        lambda: _AuthApiErrorStub("Invalid login credentials", 401),  # noqa: F841
    )
    svc = _auth_service()

    for _ in range(8):  # well beyond the default threshold of 5
        with pytest.raises(HTTPException) as ei:
            svc.login("ada@acme.com", "wrong-password")
        assert ei.value.status_code == 401
        assert ei.value.detail == "Invalid email or password."

    snap = asvc.auth_breaker.snapshot()
    assert snap["state"] == CLOSED
    assert snap["failures"] == 0
