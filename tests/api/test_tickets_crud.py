import uuid as uuidlib

from tests.conftest import U, ticket_payload


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
        "id", "uuid", "employeeId", "category", "subject", "description",
        "priority", "status", "assigneeId", "createdAt", "updatedAt",
        "firstReplyAt", "resolvedAt", "closedBy", "turns", "attachment",
    }


def test_create_ticket_strips_whitespace(api):
    payload = ticket_payload(
        U["priya"], subject="   needs new keyboard  ",
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


def test_create_ticket_unknown_employee(api):
    r = api.client.post("/api/tickets", json=ticket_payload("00000000-0000-0000-0000-999999999999"))
    assert r.status_code == 422
    assert "does not match a known user" in r.json()["detail"]


def test_create_ticket_agent_not_allowed_as_employee(api):
    r = api.client.post("/api/tickets", json=ticket_payload(U["alicia"]))
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
    created = api.client.post("/api/tickets", json=ticket_payload(U["tomas"])).json()
    r = api.client.get(f"/api/tickets/{created['uuid']}")
    assert r.status_code == 200
    assert r.json()["uuid"] == created["uuid"]


def test_get_ticket_missing(api):
    for key in ("TKT-999", "999"):
        r = api.client.get(f"/api/tickets/{key}")
        assert r.status_code == 404, key


def test_get_ticket_returns_full_thread_with_replies(api):
    r = api.client.post(
        "/api/tickets/TKT-102/replies",
        json={"authorId": U["marcus"], "text": "Actually I need two days in June."},
    )
    assert r.status_code == 200
    t = r.json()
    texts = [turn["text"] for turn in t["turns"]]
    assert texts[0] == "Looking into the carryover policy now."
    assert texts[1] == "Actually I need two days in June."
    assert [turn["role"] for turn in t["turns"]] == ["agent", "employee"]


def test_list_tickets_newest_first(api):
    api.client.post("/api/tickets", json=ticket_payload(U["dana"]))
    r = api.client.get("/api/tickets")
    ids = [t["id"] for t in r.json()]
    assert all(t["turns"] == [] for t in r.json())
    assert ids == ["TKT-104", "TKT-103", "TKT-102", "TKT-101"]
    fetched = api.client.get(f"/api/tickets/{ids[0]}").json()
    assert fetched["employeeId"] == U["dana"]


def test_list_tickets_filters(api):
    r = api.client.get("/api/tickets", params={"status": "Resolved"})
    assert [t["id"] for t in r.json()] == ["TKT-103"]

    r = api.client.get("/api/tickets", params={"category": "Leave"})
    assert [t["id"] for t in r.json()] == ["TKT-102"]

    r = api.client.get("/api/tickets", params={"priority": "Urgent"})
    assert [t["id"] for t in r.json()] == ["TKT-103"]

    r = api.client.get("/api/tickets", params={"employeeId": U["marcus"]})
    assert [t["id"] for t in r.json()] == ["TKT-102"]

    r = api.client.get("/api/tickets", params={"assigneeId": U["alicia"]})
    assert [t["id"] for t in r.json()] == ["TKT-102"]

    r = api.client.get("/api/tickets", params={"unassigned": "true"})
    assert set(t["id"] for t in r.json()) == {"TKT-101"}

    r = api.client.get("/api/tickets", params={"q": "carryover"})
    assert [t["id"] for t in r.json()] == ["TKT-102"]


def test_list_tickets_limit(api):
    r = api.client.get("/api/tickets", params={"limit": 1})
    assert len(r.json()) == 1
    assert r.json()[0]["id"] == "TKT-103"
