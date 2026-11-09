"""API-level circuit-breaker behavior for the shared PostgreSQL dependency."""

import pytest

from app import config as app_config
from app.resilience import CLOSED, OPEN, db_breaker
from tests.conftest import U, auth_headers

THRESHOLD = app_config.BREAKER_FAILURE_THRESHOLD


@pytest.fixture(autouse=True)
def _fresh_breaker():
    db_breaker.reset()
    yield
    db_breaker.reset()


def test_database_breaker_fails_fast_and_updates_health(api):
    api.fake.fail_queries = True

    for _ in range(THRESHOLD):
        response = api.client.get("/api/users")
        assert response.status_code == 502
        assert response.json()["detail"] == "Database operation failed — try again shortly."

    opened = api.client.get("/api/users")
    assert opened.status_code == 503
    assert opened.json()["detail"] == "Database is temporarily unavailable — try again shortly."

    breakers = api.client.get("/health/deps").json()["breakers"]
    assert set(breakers) == {"assistant", "db", "mailpit"}
    assert breakers["db"]["state"] == OPEN
    assert breakers["db"]["failures"] == THRESHOLD
    assert breakers["db"]["secondsUntilProbe"] > 0
    assert api.client.get("/health").status_code == 200


def test_auth_and_attachment_share_the_database_breaker(api):
    api.fake.fail_queries = True
    for _ in range(THRESHOLD):
        response = api.client.post(
            "/api/auth/login",
            json={"email": "priya@acme.com", "password": "not-a-valid-password"},
        )
        assert response.status_code == 502
    response = api.client.get("/api/tickets/TKT-101/attachment", params={"viewerId": U["alicia"]})
    assert response.status_code == 503
    assert response.json()["detail"] == "Database is temporarily unavailable — try again shortly."
    assert api.client.get("/health/deps").json()["breakers"]["db"]["state"] == OPEN


def test_service_level_422s_do_not_trip_database_breaker(api):
    """Service-side validation failures — a non-agent assignee target — are
    HTTPException 422s raised around database calls: counted as neutral by
    the breaker, never as connection failures."""
    payload = {"assigneeId": U["priya"]}  # an employee cannot be an assignee
    alicia = auth_headers("alicia")
    for _ in range(THRESHOLD * 2):
        response = api.client.patch("/api/tickets/TKT-101/assignee", json=payload, headers=alicia)
        assert response.status_code == 422

    snapshot = db_breaker.snapshot()
    assert snapshot["state"] == CLOSED
    assert snapshot["failures"] == 0
