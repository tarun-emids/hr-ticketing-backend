"""Ticket-closure feedback end to end. Identity comes from the bearer token:
only the ticket's employee can submit (a claimed userId that disagrees with
the token is a forgery 403), and only the owner or HR staff can read."""

import pytest
from fastapi import HTTPException

from app.repositories.feedback_repository import FeedbackRepository
from tests.conftest import U, auth_headers

ALICIA = auth_headers("alicia")
BEN = auth_headers("ben")
RUTH = auth_headers("ruth")


def close_ticket(api, tid, actor_key, reopen=False):
    body = {"status": "In Progress" if reopen else "Closed", "actorId": U[actor_key]}
    return api.client.patch(f"/api/tickets/{tid}/status", json=body, headers=auth_headers(actor_key))


def submit(api, tid, user_key, rating=4, comment="", **over):
    body = {"userId": U[user_key], "rating": rating, "comment": comment}
    body.update(over)
    return api.client.post(
        f"/api/tickets/{tid}/feedback", json=body, headers=auth_headers(user_key)
    )


def read(api, tid, user_key):
    return api.client.get(
        f"/api/tickets/{tid}/feedback", params={"userId": U[user_key]}, headers=auth_headers(user_key)
    )


# -- happy paths -------------------------------------------------------------


def test_first_submission_round_trips(api):
    close_ticket(api, "TKT-101", "alicia")
    r = submit(api, "TKT-101", "priya", rating=4, comment="Handled fast.")
    assert r.status_code == 201
    body = r.json()
    assert body["ticketId"] == "TKT-101"
    assert body["employeeId"] == U["priya"]
    assert body["rating"] == 4
    assert body["comment"] == "Handled fast."


def test_submission_without_comment_defaults_empty(api):
    close_ticket(api, "TKT-101", "alicia")
    r = submit(api, "TKT-101", "priya", rating=3)
    assert r.status_code == 201
    assert r.json()["comment"] == ""


def test_resubmission_replaces_row(api):
    close_ticket(api, "TKT-101", "alicia")
    submit(api, "TKT-101", "priya", rating=2, comment="slow")
    second = submit(api, "TKT-101", "priya", rating=5, comment="better now")
    assert second.status_code == 200
    assert second.json()["rating"] == 5
    rows = api.fake.execute("SELECT rating, comment FROM feedback")
    assert len(rows) == 1
    assert rows[0]["rating"] == 5
    assert rows[0]["comment"] == "better now"


def test_reopen_then_reclose_cycle(api):
    close_ticket(api, "TKT-101", "alicia")
    submit(api, "TKT-101", "priya", rating=2, comment="first closure")
    api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "In Progress", "actorId": U["ben"]},
        headers=BEN,
    )
    blocked = submit(api, "TKT-101", "priya", rating=5)
    assert blocked.status_code == 409
    close_ticket(api, "TKT-101", "ben")
    again = submit(api, "TKT-101", "priya", rating=5, comment="second closure")
    assert again.status_code == 200
    assert again.json()["rating"] == 5


# -- submission guards ---------------------------------------------------------


def test_submit_claims_are_token_derived_403(api):
    """A claimed userId that disagrees with the token is a forgery — rejected
    before the service can even classify it as 'unknown user'."""
    r = api.client.post("/api/tickets/TKT-101/feedback", json={"userId": U["marcus"], "rating": 4})
    assert r.status_code == 403


def test_submit_missing_ticket_404(api):
    assert submit(api, "TKT-999", "priya").status_code == 404


def test_submit_non_owner_403(api):
    """Marcus signs in legitimately (his own token) and tries to rate Priya's
    ticket — the SERVICE rule refuses: 'Only the ticket's employee'."""
    close_ticket(api, "TKT-101", "alicia")
    r = api.client.post(
        "/api/tickets/TKT-101/feedback",
        json={"userId": U["marcus"], "rating": 3},
        headers=auth_headers("marcus"),
    )
    assert r.status_code == 403
    assert "Only the ticket's employee" in r.json()["detail"]


def test_submit_agent_403(api):
    close_ticket(api, "TKT-101", "alicia")
    r = api.client.post(
        "/api/tickets/TKT-101/feedback",
        json={"userId": U["alicia"], "rating": 5},
        headers=ALICIA,
    )
    assert r.status_code == 403


def test_submit_resolved_ticket_409(api):
    r = submit(api, "TKT-103", "dana")
    assert r.status_code == 409
    assert "is Resolved; feedback opens" in r.json()["detail"]


def test_submit_rating_bounds_422(api):
    close_ticket(api, "TKT-101", "alicia")
    assert submit(api, "TKT-101", "priya", rating=0).status_code == 422
    assert submit(api, "TKT-101", "priya", rating=6).status_code == 422


# -- reads and read permissions -------------------------------------------------


def test_get_owner_and_any_agent_200(api):
    close_ticket(api, "TKT-101", "alicia")
    submit(api, "TKT-101", "priya", rating=4, comment="fine")
    owner = read(api, "TKT-101", "priya")
    agent = read(api, "TKT-101", "ruth")
    assert owner.status_code == agent.status_code == 200
    assert owner.json()["rating"] == 4
    assert agent.json()["ticketId"] == "TKT-101"


def test_get_by_other_employee_403(api):
    # marcus claims himself and tries to read priya's feedback row
    close_ticket(api, "TKT-101", "alicia")
    submit(api, "TKT-101", "priya", rating=4)
    r = api.client.get(
        "/api/tickets/TKT-101/feedback", params={"userId": U["marcus"]}, headers=auth_headers("marcus")
    )
    assert r.status_code == 403


def test_get_claim_forgery_403(api):
    # priya's token, marcus's userId — claim forgery, refuse before the rule
    r = api.client.get("/api/tickets/TKT-101/feedback", params={"userId": U["marcus"]})
    assert r.status_code == 403


def test_get_without_feedback_404(api):
    close_ticket(api, "TKT-101", "alicia")
    r = read(api, "TKT-101", "priya")
    assert r.status_code == 404
    assert "has no feedback" in r.json()["detail"]


def test_get_userId_is_optional_now(api):
    """The identity comes from the token: omitting userId reads the acting
    user's own feedback row (or 404 when none exists)."""
    close_ticket(api, "TKT-101", "alicia")
    r = api.client.get("/api/tickets/TKT-101/feedback", headers=auth_headers("priya"))
    assert r.status_code == 404
    assert "has no feedback" in r.json()["detail"]


# -- the database-level duplicate guarantee and the race fallback -----------------


def test_database_uniqueness_prevents_duplicates(api):
    close_ticket(api, "TKT-101", "alicia")
    repo = FeedbackRepository(api.fake)
    ticket_uuid = api.client.get(
        "/api/tickets/TKT-101", params={"viewerId": U["alicia"]}, headers=ALICIA
    ).json()["uuid"]
    row = {"ticket_id": ticket_uuid, "employee_id": U["priya"], "rating": 4, "comment": "a"}
    repo.insert_feedback(row)
    with pytest.raises(HTTPException) as err:
        repo.insert_feedback({**row, "rating": 5})
    assert err.value.status_code == 400


def test_lost_insert_race_falls_back_to_replace(api, monkeypatch):
    close_ticket(api, "TKT-101", "alicia")
    submit(api, "TKT-101", "priya", rating=2, comment="first")

    real_get = FeedbackRepository.get_for_ticket
    calls = {"n": 0}

    def blind_first_check(self, ticket_uuid):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the losing racer believed the row didn't exist
        return real_get(self, ticket_uuid)

    monkeypatch.setattr(FeedbackRepository, "get_for_ticket", blind_first_check)

    r = submit(api, "TKT-101", "priya", rating=5, comment="the racer's answer")

    assert r.status_code == 200
    assert r.json()["rating"] == 5
    rows = api.fake.execute("SELECT comment FROM feedback")
    assert len(rows) == 1
    assert rows[0]["comment"] == "the racer's answer"
