"""GET /api/tickets viewer-scoping + identity: the bearer token decides who
acts, and the server decides what each role may see. viewerId/employeeId
claims that disagree with the token are forgeries (403); out-of-scope reads
answer KB-style 403 (exists, not for you), unknowns 404. Every test goes
through the HTTP layer with real (offline-minted) bearer tokens."""

import uuid as uuidlib

import pytest

from tests.conftest import U, auth_headers, ticket_payload

ALICIA = auth_headers("alicia")
BEN = auth_headers("ben")


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


def test_ticket_list_defaults_to_the_token_identity(api):
    """viewerId is optional now: omit it and the acting identity is the
    bearer token (priya) — visible behavior identical to claiming yourself."""
    mine = api.client.get("/api/tickets")  # default client token = priya
    assert mine.status_code == 200
    assert items(mine) and all(t["employeeId"] == U["priya"] for t in items(mine))


def test_claiming_another_viewer_is_a_forgery(api):
    for claimed in ("TKT-101", "00000000-0000-0000-0000-999999999999"):
        r = api.client.get("/api/tickets", params={"viewerId": claimed})
        assert r.status_code == 403, claimed
    r = api.client.get(
        "/api/tickets", params={"viewerId": U["alicia"]}, headers=auth_headers("priya")
    )
    assert r.status_code == 403


def test_employee_sees_only_own_tickets(api):
    agent_view = api.client.get("/api/tickets", headers=ALICIA)
    mine = api.client.get("/api/tickets", params={"viewerId": U["priya"]})
    assert items(mine), "priya must see at least her seeded ticket"
    assert all(t["employeeId"] == U["priya"] for t in items(mine))
    agent_ids = {t["id"] for t in items(agent_view)}
    assert {t["id"] for t in items(mine)} <= agent_ids


def test_employee_cannot_read_others_via_query_filter(api):
    # A foreign employeeId in the filter is a tampering signal now: rejected
    # 403 instead of Anded-with-scope silence.
    r = api.client.get("/api/tickets", params={"employeeId": U["marcus"]})
    assert r.status_code == 403


def test_employee_narrows_by_status(api):
    r = api.client.get("/api/tickets", params={"status": "Resolved"})
    assert all(t["status"] == "Resolved" for t in items(r))
    assert all(t["employeeId"] == U["priya"] for t in items(r))


def test_agent_and_admin_see_all(api, admin_id):
    for headers in (ALICIA, auth_headers(admin_id)):
        r = api.client.get("/api/tickets", headers=headers)
        assert r.status_code == 200
        employees = {t["employeeId"] for t in items(r)}
        assert U["priya"] in employees and U["marcus"] in employees


def test_scope_survives_post_then_list(api):
    created = api.client.post("/api/tickets", json=ticket_payload(U["priya"])).json()
    # visible to the owner and to staff; invisible to fellow employees
    priya_view = api.client.get("/api/tickets")
    assert created["id"] in {t["id"] for t in items(priya_view)}
    alicia_view = api.client.get("/api/tickets", headers=ALICIA)
    assert created["id"] in {t["id"] for t in items(alicia_view)}
    dana_view = api.client.get("/api/tickets", headers=auth_headers("dana"))
    assert created["id"] not in {t["id"] for t in items(dana_view)}


def test_detail_defaults_to_the_token_identity(api):
    r = api.client.get("/api/tickets/TKT-101")  # priya's own seeded ticket
    assert r.status_code == 200
    assert r.json()["employeeId"] == U["priya"]


def test_employee_opens_own_ticket(api):
    r = api.client.get("/api/tickets/TKT-101", params={"viewerId": U["priya"]})
    assert r.status_code == 200
    assert r.json()["employeeId"] == U["priya"]


def test_employee_cannot_open_others_ticket(api):
    # TKT-102 is Marcus's; KB-style gate: exists, not for you -> 403 (not 404)
    r = api.client.get("/api/tickets/TKT-102")
    assert r.status_code == 403


def test_claim_on_detail_is_a_forgery_403(api):
    r = api.client.get(
        "/api/tickets/TKT-101", params={"viewerId": "00000000-0000-0000-0000-999999999999"}
    )
    assert r.status_code == 403


def test_agent_and_admin_read_any_ticket(api, admin_id):
    for headers in (ALICIA, auth_headers(admin_id)):
        r = api.client.get("/api/tickets/TKT-102", headers=headers)
        assert r.status_code == 200


def test_detail_unknown_ticket_is_404(api):
    r = api.client.get("/api/tickets/TKT-999", headers=ALICIA)
    assert r.status_code == 404


def test_employee_cannot_modify_foreign_ticket_status(api):
    # TKT-102 is Marcus's; an employee actor is staff-gated -> 403
    r = api.client.patch(
        "/api/tickets/TKT-102/status", json={"status": "Closed", "actorId": U["priya"]}
    )
    assert r.status_code == 403
    t = api.client.get("/api/tickets/TKT-102", headers=ALICIA).json()
    assert t["status"] == "In Progress"  # the write never happened


def test_agent_modifies_any_ticket_status(api):
    r = api.client.patch(
        "/api/tickets/TKT-102/status",
        json={"status": "Resolved", "actorId": U["ben"]},
        headers=BEN,
    )
    assert r.status_code == 200
    assert r.json()["closedBy"] is None


def test_admin_can_modify_any_ticket_status(api, admin_id):
    r = api.client.patch(
        "/api/tickets/TKT-102/status",
        json={"status": "Closed", "actorId": admin_id},
        headers=auth_headers(admin_id),
    )
    assert r.status_code == 200
    assert r.json()["closedBy"] == admin_id


def test_employee_cannot_reply_to_foreign_ticket(api):
    before = api.client.get("/api/tickets/TKT-102", headers=ALICIA).json()
    r = api.client.post("/api/tickets/TKT-102/replies", json={"authorId": U["priya"], "text": "hi"})
    assert r.status_code == 403
    t = api.client.get("/api/tickets/TKT-102", headers=ALICIA).json()
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
    t = api.client.get("/api/tickets/TKT-101", headers=ALICIA).json()
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
        headers=BEN,
    )
    assert r.status_code == 200
    assert r.json()["assigneeId"] == U["ruth"]
    r = api.client.get("/api/agents/workload", params={"viewerId": U["ben"]}, headers=BEN)
    assert r.status_code == 200


def test_employee_cannot_access_foreign_attachment(api):
    # upload AND read: TKT-102 (Marcus's, seeded attachment) answers 403 both ways
    r = api.client.get("/api/tickets/TKT-102/attachment", params={"viewerId": U["priya"], "ttl": 60})
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
