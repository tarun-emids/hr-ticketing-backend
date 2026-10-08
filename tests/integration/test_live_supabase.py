import uuid as uuidlib

import pytest

from tests.integration.conftest import create_ticket


pytestmark = pytest.mark.integration


def test_live_users_agents_meta(live):
    r = live["client"].get("/api/users")
    assert r.status_code == 200
    users = r.json()
    roles = {u["role"] for u in users}
    assert roles == {"employee", "agent"}

    agents = live["client"].get("/api/users/agents").json()
    assert all(a["role"] == "agent" for a in agents) and len(agents) >= 3

    meta = live["client"].get("/api/meta").json()
    assert set(meta) == {"categories", "priorities", "statuses"}


def test_live_create_get_roundtrip(live, cleanup):
    ref = create_ticket(live)
    r = live["client"].get(f"/api/tickets/{ref}")
    assert r.status_code == 200
    t = r.json()
    assert t["id"] == ref
    assert t["status"] == "Open"
    assert t["turns"] == []
    assert t["attachment"] is None
    uuidlib.UUID(t["uuid"])


def test_live_golden_flow_reply_resolve_close_reopen(live, cleanup):
    ref = create_ticket(live)
    agent = live["agents"][0]["id"]
    employee = live["employees"][0]["id"]

    r = live["client"].post(
        f"/api/tickets/{ref}/replies", json={"authorId": agent, "text": "integration flow reply"}
    )
    assert r.status_code == 200
    t = r.json()
    assert t["status"] == "In Progress"
    assert t["firstReplyAt"] is not None
    assert t["turns"][-1]["text"] == "integration flow reply"

    r = live["client"].patch(f"/api/tickets/{ref}/status", json={"status": "Resolved", "actorId": agent})
    assert r.status_code == 200 and r.json()["resolvedAt"] is not None

    r = live["client"].patch(f"/api/tickets/{ref}/status", json={"status": "Closed", "actorId": agent})
    assert r.json()["closedBy"] == agent

    r = live["client"].patch(f"/api/tickets/{ref}/status", json={"status": "Open", "actorId": agent})
    t = r.json()
    assert t["resolvedAt"] is None and t["closedBy"] is None

    r = live["client"].post(
        f"/api/tickets/{ref}/replies", json={"authorId": employee, "text": "employee reopens the thread with more info"}
    )
    assert r.json()["status"] == "Waiting on Employee"


def test_live_assign_pickup_reply(live, cleanup):
    ref = create_ticket(live)
    agent = live["agents"][1]["id"]
    r = live["client"].patch(f"/api/tickets/{ref}/assignee", json={"assigneeId": agent})
    t = r.json()
    assert t["assigneeId"] == agent
    assert t["status"] == "In Progress"
    assert t["turns"][-1]["role"] == "agent"
    assert "picked it up" in t["turns"][-1]["text"]
    assert t["firstReplyAt"] is not None


def test_live_employee_reply_waits(live, cleanup):
    ref = create_ticket(live)
    employee = live["employees"][2]["id"]
    r = live["client"].patch(f"/api/tickets/{ref}/status", json={"status": "In Progress", "actorId": live["agents"][0]["id"]})
    assert r.json()["status"] == "In Progress"
    r = live["client"].post(
        f"/api/tickets/{ref}/replies", json={"authorId": employee, "text": "adding details from the employee side"}
    )
    assert r.json()["status"] == "Waiting on Employee"


def test_live_validation_422(live, cleanup):
    employee = live["employees"][0]["id"]
    ref = create_ticket(live)

    r = live["client"].post("/api/tickets", json={
        "employeeId": employee, "category": "Benefits",
        "subject": "x", "description": "This description is longer than twenty chars.",
    })
    assert r.status_code == 422

    r = live["client"].post("/api/tickets", json={
        "employeeId": employee, "category": "NotACategory",
        "subject": "Integration invalid category",
        "description": "This description is longer than twenty chars.",
    })
    assert r.status_code == 422

    r = live["client"].patch(
        f"/api/tickets/{ref}/status", json={"status": "Done", "actorId": live["agents"][0]["id"]}
    )
    assert r.status_code == 422

    r = live["client"].post(
        f"/api/tickets/{ref}/replies",
        json={"authorId": "00000000-0000-0000-0000-999999999999", "text": "hi"},
    )
    assert r.status_code == 422


def test_live_missing_ticket_404(live):
    r = live["client"].get("/api/tickets/TKT-999999")
    assert r.status_code == 404


def test_live_list_filters_see_created_ticket(live, cleanup):
    ref_a = create_ticket(live, employee=live["employees"][0]["id"], category="Leave")
    ref_b = create_ticket(live, employee=live["employees"][1]["id"], category="Leave")

    r = live["client"].get("/api/tickets", params={"category": "Leave"})
    ids = [t["id"] for t in r.json()]
    assert ref_a in ids and ref_b in ids

    r = live["client"].get("/api/tickets", params={"employeeId": live["employees"][1]["id"]})
    assert ref_b in [t["id"] for t in r.json()]

    r = live["client"].get("/api/tickets", params={"unassigned": "true"})
    assert {ref_a, ref_b} <= {t["id"] for t in r.json()}


def test_live_attachment_roundtrip(live, cleanup):
    ref = create_ticket(live)

    r = live["client"].post(
        f"/api/tickets/{ref}/attachment",
        files={"file": ("live-test.txt", b"integration attachment payload", "text/plain")},
    )
    assert r.status_code == 200, r.text
    t = r.json()
    path = t["attachment"]["path"]
    live["paths"].append(path)
    assert path.startswith(f"{ref}/")
    assert t["attachment"]["name"] == "live-test.txt"
    assert t["attachment"]["size"] == len(b"integration attachment payload")

    r = live["client"].get(f"/api/tickets/{ref}/attachment")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "live-test.txt"
    assert body["url"] and body["url"].startswith("http")


def test_live_attachment_on_missing_ticket_404(live):
    r = live["client"].get("/api/tickets/99999/attachment")
    assert r.status_code == 404


def test_live_update_priority_category(live, cleanup):
    ref = create_ticket(live)
    r = live["client"].patch(f"/api/tickets/{ref}/priority", json={"priority": "Urgent"})
    assert r.json()["priority"] == "Urgent"
    r = live["client"].patch(f"/api/tickets/{ref}/category", json={"category": "Policy"})
    assert r.json()["category"] == "Policy"
