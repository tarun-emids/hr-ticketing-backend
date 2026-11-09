import uuid as uuidlib

from tests.conftest import U, auth_headers, ticket_payload

ALICIA = auth_headers("alicia")


def items(r):
    """The only legal reading of GET /tickets after legacy removal:
    paginated envelope -> its items list."""
    return r.json()["items"]


def test_create_ticket_returns_frontend_shape(api):
    r = api.client.post("/api/tickets", json=ticket_payload(U["priya"]))
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["id"].startswith("TKT-")
    uuidlib.UUID(t["uuid"])
    assert t["employeeId"] == U["priya"]
    assert t["category"] == "Payroll"
    assert t["priority"] == "High"
    assert t["subject"] == "May payslip missing shift allowance"
    assert t["status"] == "Open"
    assert t["assigneeId"] is None
    assert t["turns"] == []
    assert set(t.keys()) == {
        "id",
        "uuid",
        "employeeId",
        "category",
        "subject",
        "description",
        "priority",
        "status",
        "assigneeId",
        "createdAt",
        "updatedAt",
        "firstReplyAt",
        "resolvedAt",
        "closedBy",
        "turns",
        "attachment",
    }


def test_create_ticket_strips_whitespace(api):
    payload = ticket_payload(
        U["priya"],
        subject="   needs new keyboard  ",
        description="My keyboard keys W, A, S and D stopped responding this week.",
    )
    r = api.client.post("/api/tickets", json=payload)
    assert r.status_code == 201
    assert r.json()["subject"] == "needs new keyboard"
    assert r.json()["description"].endswith("this week.")


def test_create_ticket_priority_defaults_to_medium(api):
    payload = ticket_payload(U["priya"])
    del payload["priority"]
    r = api.client.post("/api/tickets", json=payload)
    assert r.status_code == 201
    assert r.json()["priority"] == "Medium"


def test_create_ticket_validation_errors(api):
    base = ticket_payload(U["priya"])
    cases = [
        ({"subject": "tiny", "description": base["description"]}, "subject"),
        ({"subject": "x" * 201, "description": base["description"]}, "subject"),
        ({"subject": base["subject"], "description": "too short"}, "description"),
        ({"subject": base["subject"], "description": "y" * 10001}, "description"),
        ({"category": "Compensation"}, "category"),
        ({"priority": "Critical"}, "priority"),
    ]
    for over, field in cases:
        r = api.client.post("/api/tickets", json={**base, **over})
        assert r.status_code == 422, f"{field}: {r.text}"
    assert "detail" in r.json()


def test_create_ticket_identity_mismatch_rejected(api):
    """A body employeeId that disagrees with the bearer token must never be
    honoured (any signed-in user can only ever file as themselves)."""
    r = api.client.post("/api/tickets", json=ticket_payload("00000000-0000-0000-0000-999999999999"))
    assert r.status_code == 403


def test_create_ticket_agent_not_allowed_as_employee(api):
    """The service-side role guard survives: a signed-in agent filing their
    own ticket id is rejected because tickets belong to employees."""
    r = api.client.post(
        "/api/tickets", json=ticket_payload(U["alicia"]), headers=auth_headers("alicia")
    )
    assert r.status_code == 422
    assert "role 'employee'" in r.json()["detail"]


def test_get_ticket_by_ref(api):
    r = api.client.get("/api/tickets/TKT-101")
    assert r.status_code == 200
    t = r.json()
    assert t["id"] == "TKT-101"
    assert t["employeeId"] == U["priya"]
    assert t["turns"] == []


def test_get_ticket_by_numeric_key(api):
    r = api.client.get("/api/tickets/101")
    assert r.status_code == 200
    assert r.json()["id"] == "TKT-101"


def test_get_ticket_by_uuid(api):
    created = api.client.post("/api/tickets", json=ticket_payload(U["priya"])).json()
    r = api.client.get(f"/api/tickets/{created['uuid']}")
    assert r.status_code == 200
    assert r.json()["uuid"] == created["uuid"]


def test_get_ticket_missing(api):
    for key in ("TKT-999", "999"):
        r = api.client.get(f"/api/tickets/{key}")
        assert r.status_code == 404, key


def test_get_ticket_returns_full_thread_with_replies(api):
    headers = auth_headers("marcus")
    r = api.client.post(
        "/api/tickets/TKT-102/replies",
        json={"authorId": U["marcus"], "text": "Actually I need two days in June."},
        headers=headers,
    )
    assert r.status_code == 200
    t = r.json()
    texts = [turn["text"] for turn in t["turns"]]
    assert texts[0] == "Looking into the carryover policy now."
    assert texts[1] == "Actually I need two days in June."
    assert [turn["role"] for turn in t["turns"]] == ["agent", "employee"]


def test_list_tickets_newest_first(api):
    api.client.post("/api/tickets", json=ticket_payload(U["priya"]))
    r = api.client.get("/api/tickets", headers=ALICIA)
    ids = [t["id"] for t in items(r)]
    assert all(t["turns"] == [] for t in items(r))
    assert ids == ["TKT-104", "TKT-103", "TKT-102", "TKT-101"]
    fetched = api.client.get(f"/api/tickets/{ids[0]}", headers=ALICIA).json()
    assert fetched["employeeId"] == U["priya"]


def test_list_tickets_employee_hard_scoped_to_self(api):
    """Employees see ONLY their own tickets — even without a filter, and a
    foreign employeeId is rejected instead of honoured."""
    api.client.post("/api/tickets", json=ticket_payload(U["priya"]))
    scoped = [t["id"] for t in items(api.client.get("/api/tickets"))]
    assert scoped == ["TKT-104", "TKT-101"]  # created above + seeded priya row

    r = api.client.get("/api/tickets", params={"employeeId": U["marcus"]})
    assert r.status_code == 403

    r = api.client.get(
        "/api/tickets", params={"employeeId": U["priya"]}, headers=auth_headers("alicia")
    )
    assert [t["id"] for t in items(r)] == ["TKT-104", "TKT-101"]


def test_list_tickets_filters(api):
    # staff token: agents may filter by anyone (or nobody) across the directory
    r = api.client.get("/api/tickets", params={"status": "Resolved"}, headers=ALICIA)
    assert [t["id"] for t in items(r)] == ["TKT-103"]

    r = api.client.get("/api/tickets", params={"category": "Leave"}, headers=ALICIA)
    assert [t["id"] for t in items(r)] == ["TKT-102"]

    r = api.client.get("/api/tickets", params={"priority": "Urgent"}, headers=ALICIA)
    assert [t["id"] for t in items(r)] == ["TKT-103"]

    r = api.client.get("/api/tickets", params={"employeeId": U["marcus"]}, headers=ALICIA)
    assert [t["id"] for t in items(r)] == ["TKT-102"]

    r = api.client.get("/api/tickets", params={"assigneeId": U["alicia"]}, headers=ALICIA)
    assert [t["id"] for t in items(r)] == ["TKT-102"]

    r = api.client.get("/api/tickets", params={"unassigned": "true"}, headers=ALICIA)
    assert set(t["id"] for t in items(r)) == {"TKT-101"}

    r = api.client.get("/api/tickets", params={"q": "carryover"}, headers=ALICIA)
    assert [t["id"] for t in items(r)] == ["TKT-102"]


def test_list_tickets_page_size(api):
    """One row per page through the envelope (deeper pagination windows live
    in test_tickets_pagination.py)."""
    r = api.client.get("/api/tickets", params={"pageSize": 1}, headers=ALICIA)
    body = r.json()
    assert len(body["items"]) == 1 and body["total"] == 3 and body["hasNext"] is True
    assert body["page"] == 1 and body["pageSize"] == 1
