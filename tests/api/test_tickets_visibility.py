"""GET /api/tickets viewer-scoping: the server, not the client, decides who
sees tickets. Every test goes through the HTTP layer (mock-auth idiom)."""

import uuid as uuidlib

import pytest

from tests.conftest import U, ticket_payload


def items(r):
    """The only legal reading of GET /tickets after legacy removal:
    paginated envelope -> its items list."""
    return r.json()["items"]


@pytest.fixture()
def admin_id(api):
    """One admin account per test, straight into the fake — same pattern as
    tests/api/test_admin.py::admin_id, because the harness seeds no admin."""
    admin_id = str(uuidlib.uuid4())
    api.fake._connection.execute(
        "INSERT INTO users (id, name, email, role) VALUES (?, ?, ?, ?)",
        (admin_id, "Ada Admin", "ada.visibility@acme.com", "admin"),
    )
    api.fake._connection.commit()
    return admin_id


def test_list_requires_viewer_id(api):
    r = api.client.get("/api/tickets")
    assert r.status_code == 422
    assert "viewerId" in r.json()["detail"]


def test_list_rejects_malformed_viewer_id(api):
    r = api.client.get("/api/tickets", params={"viewerId": "TKT-101"})
    assert r.status_code == 422


def test_list_unknown_viewer_is_404(api):
    r = api.client.get("/api/tickets", params={"viewerId": "00000000-0000-0000-0000-999999999999"})
    assert r.status_code == 404


def test_employee_sees_only_own_tickets(api):
    agent_view = api.client.get("/api/tickets", params={"viewerId": U["alicia"]})
    mine = api.client.get("/api/tickets", params={"viewerId": U["priya"]})
    assert items(mine), "priya must see at least her seeded ticket"
    assert all(t["employeeId"] == U["priya"] for t in items(mine))
    agent_ids = {t["id"] for t in items(agent_view)}
    assert {t["id"] for t in items(mine)} <= agent_ids


def test_employee_cannot_read_others_via_query_filter(api):
    # scope (priya) AND filter (marcus) -> conjunction, empty set. The old
    # behavior (employeeId as an unscoped filter) would have returned
    # marcus's ticket TKT-102.
    r = api.client.get("/api/tickets", params={"viewerId": U["priya"], "employeeId": U["marcus"]})
    assert items(r) == []


def test_employee_narrows_by_status(api):
    r = api.client.get("/api/tickets", params={"viewerId": U["priya"], "status": "Resolved"})
    assert all(t["status"] == "Resolved" for t in items(r))
    assert all(t["employeeId"] == U["priya"] for t in items(r))


def test_agent_and_admin_see_all(api, admin_id):
    for viewer in (U["alicia"], admin_id):
        r = api.client.get("/api/tickets", params={"viewerId": viewer})
        assert r.status_code == 200
        employees = {t["employeeId"] for t in items(r)}
        assert U["priya"] in employees and U["marcus"] in employees


def test_scope_survives_post_then_list(api):
    created = api.client.post("/api/tickets", json=ticket_payload(U["dana"])).json()
    dana_view = api.client.get("/api/tickets", params={"viewerId": U["dana"]})
    assert created["id"] in {t["id"] for t in items(dana_view)}
    marcus_view = api.client.get("/api/tickets", params={"viewerId": U["marcus"]})
    assert created["id"] not in {t["id"] for t in items(marcus_view)}


def test_detail_requires_viewer_id(api):
    r = api.client.get("/api/tickets/TKT-101")
    assert r.status_code == 422


def test_detail_unknown_viewer_is_404(api):
    r = api.client.get(
        "/api/tickets/TKT-101", params={"viewerId": "00000000-0000-0000-0000-999999999999"}
    )
    assert r.status_code == 404


def test_employee_opens_own_ticket(api):
    r = api.client.get("/api/tickets/TKT-101", params={"viewerId": U["priya"]})
    assert r.status_code == 200
    assert r.json()["employeeId"] == U["priya"]


def test_employee_cannot_open_others_ticket(api):
    # TKT-102 is Marcus's; KB-style gate: exists, not for you -> 403 (not 404)
    r = api.client.get("/api/tickets/TKT-102", params={"viewerId": U["priya"]})
    assert r.status_code == 403


def test_agent_and_admin_read_any_ticket(api, admin_id):
    for viewer in (U["alicia"], admin_id):
        r = api.client.get("/api/tickets/TKT-102", params={"viewerId": viewer})
        assert r.status_code == 200


def test_detail_unknown_ticket_is_404(api):
    r = api.client.get("/api/tickets/TKT-999", params={"viewerId": U["alicia"]})
    assert r.status_code == 404


def test_employee_cannot_modify_foreign_ticket_status(api):
    # TKT-102 is Marcus's; an employee actor is filtered by scope -> 403
    r = api.client.patch(
        "/api/tickets/TKT-102/status", json={"status": "Closed", "actorId": U["priya"]}
    )
    assert r.status_code == 403
    t = api.client.get("/api/tickets/TKT-102", params={"viewerId": U["alicia"]}).json()
    assert t["status"] == "In Progress"  # the write never happened


def test_agent_modifies_any_ticket_status(api):
    r = api.client.patch(
        "/api/tickets/TKT-102/status", json={"status": "Resolved", "actorId": U["ben"]}
    )
    assert r.status_code == 200
    assert r.json()["closedBy"] is None


def test_admin_can_modify_any_ticket_status(api, admin_id):
    r = api.client.patch(
        "/api/tickets/TKT-102/status", json={"status": "Closed", "actorId": admin_id}
    )
    assert r.status_code == 200
    assert r.json()["closedBy"] == admin_id


def test_employee_cannot_reply_to_foreign_ticket(api):
    before = api.client.get("/api/tickets/TKT-102", params={"viewerId": U["alicia"]}).json()
    r = api.client.post("/api/tickets/TKT-102/replies", json={"authorId": U["priya"], "text": "hi"})
    assert r.status_code == 403
    t = api.client.get("/api/tickets/TKT-102", params={"viewerId": U["alicia"]}).json()
    assert t["turns"] == before["turns"]  # thread content: identical, nothing added
    assert all(turn["authorId"] != U["priya"] for turn in t["turns"])


def test_employee_replies_to_own_ticket_allowed(api):
    r = api.client.post("/api/tickets/TKT-101/replies", json={"authorId": U["priya"], "text": "hi"})
    assert r.status_code == 200
    assert r.json()["status"] == "Waiting on Employee"


def test_employee_cannot_assign(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/assignee",
        params={"viewerId": U["priya"]},
        json={"assigneeId": U["priya"]},
    )
    assert r.status_code == 403
    t = api.client.get("/api/tickets/TKT-101", params={"viewerId": U["alicia"]}).json()
    assert t["assigneeId"] is None


def test_employee_cannot_set_priority_or_category(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/priority",
        params={"viewerId": U["priya"]},
        json={"priority": "Urgent"},
    )
    assert r.status_code == 403
    r = api.client.patch(
        "/api/tickets/TKT-101/category",
        params={"viewerId": U["priya"]},
        json={"category": "Leave"},
    )
    assert r.status_code == 403


def test_employee_cannot_auto_assign_or_read_workload(api):
    r = api.client.post("/api/tickets/TKT-101/auto-assign", params={"viewerId": U["priya"]})
    assert r.status_code == 403
    r = api.client.get("/api/agents/workload", params={"viewerId": U["priya"]})
    assert r.status_code == 403


def test_agent_can_assign_and_read_workload(api):
    r = api.client.patch(
        "/api/tickets/TKT-101/assignee",
        params={"viewerId": U["ben"]},
        json={"assigneeId": U["ruth"]},
    )
    assert r.status_code == 200
    assert r.json()["assigneeId"] == U["ruth"]
    r = api.client.get("/api/agents/workload", params={"viewerId": U["ben"]})
    assert r.status_code == 200


def test_employee_cannot_access_foreign_attachment(api):
    # upload AND read: TKT-102 (Marcus's, seeded attachment) answers 403 both ways
    r = api.client.get(
        "/api/tickets/TKT-102/attachment", params={"viewerId": U["priya"], "ttl": 60}
    )
    assert r.status_code == 403


def test_employee_reads_own_attachment(api):
    r = api.client.post(
        "/api/tickets",
        json={
            "employeeId": U["priya"],
            "category": "Payroll",
            "subject": "Payslip shows wrong overtime rate",
            "description": "The overtime rate on this month's payslip reflects the old band.",
        },
    )
    tid = r.json()["id"]
    r = api.client.post(
        f"/api/tickets/{tid}/attachment",
        params={"viewerId": U["priya"]},
        files={"file": ("notes.txt", b"attachment bytes", "text/plain")},
    )
    assert r.status_code == 200
    r = api.client.get(f"/api/tickets/{tid}/attachment", params={"viewerId": U["priya"]})
    assert r.status_code == 200
    assert r.json()["name"] == "notes.txt"
