"""API-level breaker behavior through the real endpoint stack, offline.

The `api` fixture (tests/conftest.py) wires the FakeSupabase in place of the
real client, so endpoints run exactly as in production — only the network is
faked. These tests drive the REAL module-level breakers (shipped default
threshold) against injected failure sources and assert fast-fail 503s,
/health/deps state changes, and surface independence."""

import io

import pytest
from postgrest.exceptions import APIError

from app import config as app_config
from app.resilience import CLOSED, OPEN, db_breaker, storage_breaker
from tests.conftest import U, ticket_payload

THRESHOLD = app_config.BREAKER_FAILURE_THRESHOLD  # shipped default (env-tunable)


@pytest.fixture(autouse=True)
def _fresh_breakers():
    for brk in (db_breaker, storage_breaker):
        brk.reset()
    yield
    for brk in (db_breaker, storage_breaker):
        brk.reset()


class _BrokenBuilder:
    """Every chained call returns itself; .execute() raises like a failing
    PostgREST endpoint would (non-constraint SQL state — run() maps exactly
    this class to a 502 today). The raise lands inside run()'s
    db_breaker.call(q.execute), where a real outage would land."""

    def __getattr__(self, name):
        return lambda *a, **kw: self

    def execute(self):
        raise APIError({"message": "postgrest internally down", "code": "XX000"})


class _DeadDB:
    def table(self, name):
        return _BrokenBuilder()


def test_db_breaker_fails_fast_and_health_deps_reflects_it(api, monkeypatch):
    monkeypatch.setattr(app_config, "get_client", lambda: _DeadDB())

    # THRESHOLD failing requests surface as the same 502 they do today —
    # mapped through run() (Database rejected the write: ...)
    for _ in range(THRESHOLD):
        r = api.client.get("/api/users")
        assert r.status_code == 502
        assert "Database rejected the write" in r.json()["detail"]

    # threshold reached: everything database-backed is now an instant 503
    r_open = api.client.get("/api/users")
    assert r_open.status_code == 503
    assert r_open.json()["detail"] == "Database is temporarily unavailable — try again shortly."

    deps = api.client.get("/health/deps").json()["breakers"]
    assert deps["db"]["state"] == OPEN
    assert deps["db"]["failures"] == THRESHOLD
    assert deps["auth"]["state"] == CLOSED  # surfaces are independent
    assert deps["db"]["secondsUntilProbe"] > 0

    # /health stays pure liveness, no Supabase touch, even mid-outage
    assert api.client.get("/health").status_code == 200


def test_storage_breaker_fails_fast_independently_of_db(api):
    api.fake.fail_uploads = True  # FakeStorage.upload raises like Storage down

    upload = lambda: api.client.post(  # noqa: E731
        "/api/tickets/TKT-101/attachment",
        files={"file": ("notes.txt", io.BytesIO(b"payload"), "text/plain")},
    )

    for _i in range(THRESHOLD):
        r = upload()
        assert r.status_code == 502
        assert "Storage upload failed" in r.json()["detail"]

    # threshold reached: instant 503 without a single further storage attempt
    r_open = upload()
    assert r_open.status_code == 503
    assert (
        r_open.json()["detail"]
        == "Attachment storage is temporarily unavailable — try again shortly."
    )

    deps = api.client.get("/health/deps").json()["breakers"]
    assert deps["storage"]["state"] == OPEN
    assert deps["storage"]["failures"] == THRESHOLD

    # the database surface is untouched by the storage outage: reads keep
    # working while attachments are degraded
    r_tickets = api.client.get("/api/tickets")
    assert r_tickets.status_code == 200
    assert db_breaker.snapshot() == {"name": "db", "state": CLOSED, "failures": 0}


def test_service_level_422s_do_not_trip_the_db_breaker(api):
    """Validation failures (unknown employee -> 422) mean the database ANSWERED
    its lookups fine — failed requests alone must never trip the circuit."""
    payload = ticket_payload(U["priya"], employeeId="dfde0b26-0000-0000-0000-000000000000")
    for _ in range(THRESHOLD * 2):
        r = api.client.post("/api/tickets", json=payload)
        assert r.status_code == 422

    snap = db_breaker.snapshot()
    assert snap["state"] == CLOSED
    assert snap["failures"] == 0
