import pytest
from fastapi import HTTPException

from app.repositories.feedback_repository import FeedbackRepository
from tests.conftest import U

UNKNOWN_USER = "00000000-0000-0000-0000-999999999999"


def close_ticket(api, tid, actor):
    return api.client.patch(
        f"/api/tickets/{tid}/status", json={"status": "Closed", "actorId": actor}
    )


def submit(api, tid, user, rating=4, **over):
    body = {"userId": user, "rating": rating}
    body.update(over)
    return api.client.post(f"/api/tickets/{tid}/feedback", json=body)


def read(api, tid, user):
    return api.client.get(f"/api/tickets/{tid}/feedback", params={"userId": user})


# -- happy paths -------------------------------------------------------------


def test_first_submission_round_trips(api):
    close_ticket(api, 'TKT-101', U["alicia"])
    r = submit(api, 'TKT-101', U['priya'], rating=4, comment="Handled fast.")
    assert r.status_code == 201
    body = r.json()
    assert body["ticketId"] == "TKT-101"
    assert body["employeeId"] == U['priya']
    assert body["rating"] == 4
    assert body["comment"] == "Handled fast."


def test_submission_without_comment_defaults_empty(api):
    close_ticket(api, "TKT-101", U["alicia"])
    r = submit(api, "TKT-101", U["priya"], rating=3)
    assert r.status_code == 201
    assert r.json()["comment"] == ""


def test_resubmission_replaces_row(api):
    close_ticket(api, "TKT-101", U["alicia"])
    submit(api, "TKT-101", U["priya"], rating=2, comment="slow")
    second = submit(api, "TKT-101", U["priya"], rating=5, comment="better now")
    assert second.status_code == 200
    assert second.json()["rating"] == 5
    rows = api.fake.execute("SELECT rating, comment FROM feedback")
    assert len(rows) == 1
    assert rows[0]["rating"] == 5
    assert rows[0]["comment"] == "better now"


def test_reopen_then_reclose_cycle(api):
    close_ticket(api, "TKT-101", U["alicia"])
    submit(api, "TKT-101", U["priya"], rating=2, comment="first closure")
    api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "In Progress", "actorId": U["ben"]},
    )
    blocked = submit(api, "TKT-101", U["priya"], rating=5)
    assert blocked.status_code == 409
    close_ticket(api, "TKT-101", U["ben"])
    again = submit(api, "TKT-101", U["priya"], rating=5, comment="second closure")
    assert again.status_code == 200
    assert again.json()["rating"] == 5


# -- submission guards ---------------------------------------------------------


def test_submit_missing_ticket_404(api):
    assert submit(api, "TKT-999", U["priya"]).status_code == 404


def test_submit_unknown_user_403(api):
    close_ticket(api, "TKT-101", U["alicia"])
    r = submit(api, "TKT-101", UNKNOWN_USER)
    assert r.status_code == 403
    assert r.json()["detail"] == "Unknown user."


def test_submit_non_owner_403(api):
    close_ticket(api, "TKT-101", U["alicia"])
    r = submit(api, "TKT-101", U["marcus"])
    assert r.status_code == 403
    assert "Only the ticket's employee" in r.json()["detail"]


def test_submit_agent_403(api):
    close_ticket(api, "TKT-101", U["alicia"])
    r = submit(api, "TKT-101", U["alicia"])
    assert r.status_code == 403


def test_submit_resolved_ticket_409(api):
    r = submit(api, "TKT-103", U["dana"])
    assert r.status_code == 409
    assert "is Resolved; feedback opens" in r.json()["detail"]


def test_submit_rating_bounds_422(api):
    close_ticket(api, "TKT-101", U["alicia"])
    assert submit(api, "TKT-101", U["priya"], rating=0).status_code == 422
    assert submit(api, "TKT-101", U["priya"], rating=6).status_code == 422


# -- reads and read permissions -------------------------------------------------


def test_get_owner_and_any_agent_200(api):
    close_ticket(api, "TKT-101", U["alicia"])
    submit(api, "TKT-101", U["priya"], rating=4, comment="fine")
    owner = read(api, "TKT-101", U["priya"])
    agent = read(api, "TKT-101", U["ruth"])
    assert owner.status_code == agent.status_code == 200
    assert owner.json()["rating"] == 4
    assert agent.json()["ticketId"] == "TKT-101"


def test_get_other_employee_403(api):
    close_ticket(api, "TKT-101", U["alicia"])
    submit(api, "TKT-101", U["priya"], rating=4)
    assert read(api, "TKT-101", U["marcus"]).status_code == 403


def test_get_without_feedback_404(api):
    close_ticket(api, "TKT-101", U["alicia"])
    r = read(api, "TKT-101", U["priya"])
    assert r.status_code == 404
    assert "has no feedback" in r.json()["detail"]


def test_get_unknown_user_403(api):
    assert read(api, "TKT-101", UNKNOWN_USER).status_code == 403


def test_get_missing_user_id_422(api):
    r = api.client.get("/api/tickets/TKT-101/feedback")
    assert r.status_code == 422


# -- the database-level duplicate guarantee and the race fallback -----------------


def test_database_uniqueness_prevents_duplicates(api):
    close_ticket(api, "TKT-101", U["alicia"])
    repo = FeedbackRepository(api.fake)
    ticket_uuid = api.client.get("/api/tickets/TKT-101").json()["uuid"]
    row = {"ticket_id": ticket_uuid, "employee_id": U["priya"], "rating": 4, "comment": "a"}
    repo.insert_feedback(row)
    with pytest.raises(HTTPException) as err:
        repo.insert_feedback({**row, "rating": 5})
    assert err.value.status_code == 400


def test_lost_insert_race_falls_back_to_replace(api, monkeypatch):
    close_ticket(api, "TKT-101", U["alicia"])
    submit(api, "TKT-101", U["priya"], rating=2, comment="first")

    real_get = FeedbackRepository.get_for_ticket
    calls = {"n": 0}

    def blind_first_check(self, ticket_uuid):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the losing racer believed the row didn't exist
        return real_get(self, ticket_uuid)

    monkeypatch.setattr(FeedbackRepository, "get_for_ticket", blind_first_check)

    r = submit(api, "TKT-101", U["priya"], rating=5, comment="the racer's answer")

    assert r.status_code == 200
    assert r.json()["rating"] == 5
    rows = api.fake.execute("SELECT comment FROM feedback")
    assert len(rows) == 1
    assert rows[0]["comment"] == "the racer's answer"
