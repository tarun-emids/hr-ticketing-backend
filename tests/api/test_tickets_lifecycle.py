"""Ticket lifecycle/assignee/priority/category — staff workflow endpoints
require an AGENT (or admin) bearer token; the acting user always comes from
the token (a body actorId that disagrees, or a viewerId claim that does, is
rejected), while replies derive their author the same way. Cover views (job
reads) may be made by staff tokens as well."""

from uuid import UUID

from app.repositories.user_repository import UserRepository
from tests.conftest import U, auth_headers

ALICIA = auth_headers("alicia")
BEN = auth_headers("ben")
RUTH = auth_headers("ruth")


def reply(api, tid, key, text="Replying right here."):
    """Author = the bearer-token identity: post as the named seeded user."""
    return api.client.post(
        f"/api/tickets/{tid}/replies",
        json={"authorId": U[key], "text": text},
        headers=auth_headers(key),
    )


def ticket_by_ref(api, tid, key="alicia"):
    return api.client.get(f"/api/tickets/{tid}", headers=auth_headers(key)).json()


def test_agent_first_reply_stamps_and_moves_to_in_progress(api):
    before = ticket_by_ref(api, "TKT-101")
    assert before["firstReplyAt"] is None
    assert before["status"] == "Open"

    r = reply(api, "TKT-101", "alicia")
    assert r.status_code == 200
    t = r.json()
    assert t["status"] == "In Progress"
    assert t["firstReplyAt"] is not None
    assert t["turns"][-1]["role"] == "agent"
    assert t["turns"][-1]["authorId"] == U["alicia"]


def test_second_agent_reply_keeps_first_reply_at(api):
    after_first = ticket_by_ref(api, "TKT-102", key="ben")
    stamp = after_first["firstReplyAt"]
    r = reply(api, "TKT-102", "ben")
    t = r.json()
    assert t["firstReplyAt"] == stamp


def test_employee_reply_moves_active_ticket_to_waiting_on_employee(api):
    api.client.post(
        "/api/tickets",
        json={
            "employeeId": U["priya"],
            "category": "Benefits",
            "subject": "Dental plan covers orthodontics?",
            "description": "Does the new dental plan cover partial orthodontic treatment, and where do I check coverage?",
        },
    )
    from tests.conftest import auth_headers as ah

    created = api.client.get("/api/tickets", headers=ah("priya")).json()["items"][0]["id"]
    r = reply(api, created, "priya")
    t = r.json()
    assert t["status"] == "Waiting on Employee"
    assert t["firstReplyAt"] is None


def test_employee_reply_leaves_final_statuses_alone(api):
    r = reply(api, "TKT-103", "dana")
    assert r.json()["status"] == "Resolved"


def test_reply_identity_bearer_wins(api):
    """A signed-in user replying under another identity is rejected — the
    author is fixed by the token, never by the body."""
    api.client.post(
        "/api/tickets",
        json={
            "employeeId": U["priya"],
            "category": "Other",
            "subject": "Foreign author probe ticket",
            "description": "Probe ticket to verify foreign author ids are rejected server-side.",
        },
    )
    created_id = api.client.get("/api/tickets").json()["items"][0]["id"]
    r = api.client.post(
        f"/api/tickets/{created_id}/replies",
        json={"authorId": U["marcus"], "text": "forged author"},
    )
    assert r.status_code == 403


def test_employee_cannot_reply_to_foreign_ticket(api):
    """The service-side viewable gate also covers replies (Soha's contract):
    an employee can never write into somebody else's thread."""
    r = api.client.post("/api/tickets/TKT-102/replies", json={"authorId": U["priya"], "text": "hi"})
    assert r.status_code == 403


def test_reply_empty_text_rejected(api):
    r = reply(api, "TKT-101", "priya", text="")
    assert r.status_code == 422


def test_reply_to_missing_ticket(api):
    r = reply(api, "TKT-999", "priya")
    assert r.status_code == 404


def test_resolve_stamps_resolved_at(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Resolved", "actorId": U["ben"]},
        headers=BEN,
    )
    t = r.json()
    assert t["status"] == "Resolved"
    assert t["resolvedAt"] is not None
    assert t["closedBy"] is None


def test_close_records_actor_keeps_resolved_at(api):
    resolved = api.client.patch(
        "/api/tickets/TKT-103/status",
        json={"status": "Closed", "actorId": U["ruth"]},
        headers=RUTH,
    ).json()
    assert resolved["closedBy"] == U["ruth"]
    assert resolved["resolvedAt"] is not None


def test_close_from_open_stamps_both(api):
    t = api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Closed", "actorId": U["ben"]},
        headers=BEN,
    ).json()
    assert t["closedBy"] == U["ben"]
    assert t["resolvedAt"] is not None


def test_reopening_clears_resolved_at_and_closed_by(api):
    api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Resolved", "actorId": U["ben"]},
        headers=BEN,
    )
    api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "In Progress", "actorId": U["ben"]},
        headers=BEN,
    )
    t = ticket_by_ref(api, "TKT-101")
    assert t["resolvedAt"] is None
    assert t["closedBy"] is None


def test_waiting_on_employee_keeps_timestamps(api):
    api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Resolved", "actorId": U["ben"]},
        headers=BEN,
    )
    stamp = ticket_by_ref(api, "TKT-101")["resolvedAt"]
    t = api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Waiting on Employee", "actorId": U["ben"]},
        headers=BEN,
    ).json()
    assert t["status"] == "Waiting on Employee"
    assert t["resolvedAt"] == stamp
    assert t["closedBy"] is None


def test_status_invalid_value(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Done", "actorId": U["ben"]},
        headers=BEN,
    )
    assert r.status_code == 422


def test_status_rejected_for_employee_token(api):
    """Workflow routes are staff-only: an employee token cannot move a
    ticket's status at all (agent or admin tokens only)."""
    r = api.client.patch(
        "/api/tickets/TKT-101/status", json={"status": "Resolved", "actorId": U["priya"]}
    )
    assert r.status_code == 403


def test_status_actor_mismatch_rejected(api):
    """Even for staff, the closed-by actor is the token identity — a body
    actorId pointing at someone else is a forgery attempt."""
    r = api.client.patch(
        "/api/tickets/TKT-101/status",
        json={"status": "Resolved", "actorId": "00000000-0000-0000-0000-999999999999"},
        headers=BEN,
    )
    assert r.status_code == 403


def test_assign_to_unanswered_ticket_posts_pickup_reply(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/assignee", json={"assigneeId": U["alicia"]}, headers=ALICIA
    )
    t = r.json()
    assert t["assigneeId"] == U["alicia"]
    assert t["firstReplyAt"] is not None
    assert t["status"] == "In Progress"
    pickup = t["turns"][-1]
    assert pickup["authorId"] == U["alicia"]
    assert pickup["role"] == "agent"
    assert pickup["text"] == (
        "Thanks for raising this — I've picked it up and will get back to you shortly."
    )


def test_auto_assign_uses_postgresql_uuid_agent_ids(api, monkeypatch):
    agents = UserRepository.agents

    def agents_with_uuid_ids(repository):
        rows = agents(repository)
        for row in rows:
            row["id"] = UUID(row["id"])
        return rows

    monkeypatch.setattr(UserRepository, "agents", agents_with_uuid_ids)
    workload = api.client.get("/api/agents/workload", headers=ALICIA)
    assert workload.status_code == 200
    assert len(workload.json()) == 3

    response = api.client.post("/api/tickets/TKT-101/auto-assign", headers=ALICIA)
    assert response.status_code == 200, response.text
    ticket = response.json()
    assert ticket["assigneeId"] in {agent["id"] for agent in workload.json()}
    assert ticket["routedTo"]["id"] == ticket["assigneeId"]
    assert ticket["status"] == "In Progress"
    assert ticket["turns"][-1]["role"] == "agent"


def test_user_lookup_accepts_postgresql_uuid(api):
    user = UserRepository(api.fake).get_by_id(UUID(U["ben"]))
    assert user is not None
    assert user["id"] == U["ben"]


def test_assign_to_already_replied_ticket_no_duplicate_pickup(api):
    before = ticket_by_ref(api, "TKT-102", key="ben")
    stamp = before["firstReplyAt"]
    r = api.client.patch(
        "/api/tickets/TKT-102/assignee", json={"assigneeId": U["ben"]}, headers=ALICIA
    )
    t = r.json()
    assert t["assigneeId"] == U["ben"]
    assert t["firstReplyAt"] == stamp
    assert len(t["turns"]) == 1
    assert t["status"] == "In Progress"


def test_unassign(api):
    r = api.client.patch(
        "/api/tickets/TKT-102/assignee", json={"assigneeId": None}, headers=ALICIA
    )
    assert r.json()["assigneeId"] is None


def test_assign_unknown_user(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/assignee", json={"assigneeId": U["priya"]}, headers=ALICIA
    )
    assert r.status_code == 422
    assert "must be an HR agent" in r.json()["detail"]


def test_workload_rejected_for_employee_token(api):
    assert api.client.get("/api/agents/workload").status_code == 403


def test_set_priority_and_category(api):
    t = api.client.patch(
        "/api/tickets/TKT-101/priority", json={"priority": "Urgent"}, headers=ALICIA
    ).json()
    assert t["priority"] == "Urgent"
    t = api.client.patch(
        "/api/tickets/TKT-101/category", json={"category": "Leave"}, headers=ALICIA
    ).json()
    assert t["category"] == "Leave"


def test_set_priority_invalid(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/priority", json={"priority": "Someday"}, headers=ALICIA
    )
    assert r.status_code == 422


def test_set_category_invalid(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/category", json={"category": "Wages"}, headers=ALICIA
    )
    assert r.status_code == 422


def test_updates_bump_updated_at(api):
    before = ticket_by_ref(api, "TKT-101")["updatedAt"]
    api.client.patch("/api/tickets/TKT-101/priority", json={"priority": "Low"}, headers=ALICIA)
    after = ticket_by_ref(api, "TKT-101")["updatedAt"]
    assert after > before
