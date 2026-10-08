"""Notifications API: flows, isolation, pagination, failure isolation."""
from datetime import datetime, timedelta, timezone

from tests.conftest import U

AGENTS = [U["alicia"], U["ben"], U["ruth"]]


def list_for(api, uid, **params):
    return api.client.get("/api/notifications", params={"userId": uid, **params}).json()


def unread_of(api, uid):
    return api.client.get("/api/notifications/unread-count", params={"userId": uid}).json()["unread"]


def create_employee_ticket(api, employee, **over):
    body = {
        "employeeId": employee,
        "category": "Payroll",
        "subject": "Shift allowance missing on May payslip",
        "description": "The May payslip does not include the 12 weekend shift hours I worked.",
        **over,
    }
    r = api.client.post("/api/tickets", json=body)
    assert r.status_code == 201
    return r.json()


def test_new_ticket_notifies_every_agent_with_generic_message(api):
    created = create_employee_ticket(api, U["priya"])
    ref = created["id"]

    for agent in AGENTS:
        rows = [n for n in list_for(api, agent) if n["ticketRef"] == ref]
        assert len(rows) == 1, f"agent {agent} should have exactly one notification"
        row = rows[0]
        assert row["type"] == "ticket_created"
        assert row["read"] is False
        assert row["recipientId"] == agent
        assert row["message"].startswith("New Payroll ticket")
        assert ref in row["message"]
        assert "confidential" not in row["message"]

    # the employee who filed it hears nothing about their own action
    assert [n for n in list_for(api, U["priya"]) if n["ticketRef"] == ref] == []


def test_employee_reply_on_unassigned_ticket_reaches_all_agents(api):
    ref = create_employee_ticket(api, U["priya"])["id"]
    api.client.post(
        f"/api/tickets/{ref}/replies",
        json={"authorId": U["priya"], "text": "Adding the shift roster as proof meanwhile."},
    )

    for agent in AGENTS:
        rows = [
            n for n in list_for(api, agent)
            if n["ticketRef"] == ref and n["type"] == "ticket_reply"
        ]
        assert len(rows) == 1
    assert list_for(api, U["priya"]) == []  # author never self-notified


def test_agent_reply_notifies_owner_only(api):
    ref = "TKT-102"  # Marcus' ticket, assigned to Alicia
    r = api.client.post(
        f"/api/tickets/{ref}/replies",
        json={"authorId": U["alicia"], "text": "Checking the carry-over policy now."},
    )
    assert r.status_code == 200

    rows = [n for n in list_for(api, U["marcus"]) if n["ticketRef"] == ref]
    assert [n["type"] for n in rows] == ["ticket_reply"]
    assert "Alicia" in rows[0]["message"]
    assert [n for n in list_for(api, U["alicia"]) if n["ticketRef"] == ref and n["type"] == "ticket_reply"] == []


def test_assignment_notifies_assignee_only_on_change(api):
    ref = create_employee_ticket(api, U["priya"])["id"]
    api.client.patch(f"/api/tickets/{ref}/assignee", json={"assigneeId": U["ben"]})
    assert len([n for n in list_for(api, U["ben"]) if n["ticketRef"] == ref]) == 1

    # re-picking the same assignee stays quiet
    api.client.patch(f"/api/tickets/{ref}/assignee", json={"assigneeId": U["ben"]})
    assert len([n for n in list_for(api, U["ben"]) if n["ticketRef"] == ref]) == 1

    # clearing the assignee notifies nobody
    api.client.patch(f"/api/tickets/{ref}/assignee", json={"assigneeId": None})
    assert len([n for n in list_for(api, U["ben"]) if n["ticketRef"] == ref]) == 1


def test_status_change_excludes_actor_and_third_parties(api):
    ref = "TKT-103"  # Dana's ticket, assigned to Ben
    r = api.client.patch(f"/api/tickets/{ref}/status", json={"status": "Resolved", "actorId": U["ben"]})
    assert r.status_code == 200

    dana_rows = [n for n in list_for(api, U["dana"]) if n["ticketRef"] == ref]
    assert [n["type"] for n in dana_rows] == ["ticket_status_changed"]
    assert "resolved" in dana_rows[0]["message"]

    # the acting agent must not be notified for their own action
    assert [n for n in list_for(api, U["ben"]) if n["ticketRef"] == ref] == []
    # third-party agents stay quiet too
    assert [n for n in list_for(api, U["ruth"]) if n["ticketRef"] == ref] == []


def test_draft_submit_notifies_agents(api):
    d = api.client.post("/api/drafts", json={"employeeId": U["tomas"], "category": "Leave"}).json()
    api.client.patch(
        f"/api/drafts/{d['id']}",
        params={"employeeId": U["tomas"]},
        json={
            "subject": "Carry over unused PTO days",
            "description": "Four unused PTO days from last year are expiring soon — can they carry over?",
        },
    )
    r = api.client.post(f"/api/drafts/{d['id']}/submit", json={"employeeId": U["tomas"]})
    assert r.status_code == 200
    ref = r.json()["id"]

    for agent in AGENTS:
        assert [n["type"] for n in list_for(api, agent) if n["ticketRef"] == ref] == ["ticket_created"]


def test_unread_count_read_one_and_read_all(api):
    ref1 = create_employee_ticket(api, U["priya"])["id"]
    create_employee_ticket(api, U["priya"])

    assert unread_of(api, U["ben"]) == 2
    notif_id = [n for n in list_for(api, U["ben"]) if n["ticketRef"] == ref1][0]["id"]

    r = api.client.post(f"/api/notifications/{notif_id}/read", json={"userId": U["ben"]})
    assert r.status_code == 200
    assert r.json()["read"] is True and r.json()["readAt"]
    assert unread_of(api, U["ben"]) == 1

    r = api.client.post("/api/notifications/read-all", json={"userId": U["ben"]})
    assert r.json()["updated"] == 1
    assert unread_of(api, U["ben"]) == 0

    all_rows = list_for(api, U["ben"])
    assert len(all_rows) == 2 and all(n["read"] for n in all_rows)
    # Alicia's copy is untouched
    assert unread_of(api, U["alicia"]) == 2


def test_strict_own_notifications_isolation(api):
    create_employee_ticket(api, U["priya"])
    agent_rows = list_for(api, U["ben"])
    assert all(n["recipientId"] == U["ben"] for n in agent_rows)

    # Priya cannot read-mark Ben's notification
    notif_id = agent_rows[0]["id"]
    r = api.client.post(f"/api/notifications/{notif_id}/read", json={"userId": U["priya"]})
    assert r.status_code == 404

    # read-all only touches the acting user's rows
    api.client.post("/api/notifications/read-all", json={"userId": U["priya"]})
    assert unread_of(api, U["ben"]) == 1


def test_pagination_and_state_filter(api):
    for _ in range(3):
        create_employee_ticket(api, U["priya"])

    page = list_for(api, U["ruth"], limit=2)
    assert len(page) == 2
    page2 = list_for(api, U["ruth"], limit=2, offset=2)
    assert len(page2) == 1

    everything = {n["id"] for n in list_for(api, U["ruth"], limit=100)}
    assert {n["id"] for n in page + page2} == everything

    unread_page = list_for(api, U["ruth"], state="unread", limit=100)
    assert len(unread_page) == 3
    api.client.post("/api/notifications/read-all", json={"userId": U["ruth"]})
    assert list_for(api, U["ruth"], state="unread") == []
    assert len(list_for(api, U["ruth"]) ) == 3  # read ones still listed in 'all'


def test_endpoint_validation(api):
    assert api.client.get("/api/notifications", params={"userId": "no-such-user"}).status_code == 422
    assert api.client.get("/api/notifications", params={"userId": U["ben"], "state": "bogus"}).status_code == 422
    assert api.client.get("/api/notifications", params={"userId": U["ben"], "limit": 0}).status_code == 422
    assert api.client.get("/api/notifications/unread-count", params={"userId": "no-such-user"}).status_code == 422


def test_notification_failure_never_blocks_ticket_write(api, monkeypatch):
    def boom(_payload):
        raise RuntimeError("notifications table down")

    monkeypatch.setattr(api.fake.notifications, "on_insert", boom)
    created = create_employee_ticket(api, U["priya"])
    assert created["id"], "a notifications outage must never break ticket creation"
    assert unread_of(api, U["ben"]) == 0
    assert unread_of(api, U["alicia"]) == 0


def _age(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _ticket_row(ref, priority, hours_old, seq):
    return {
        "id": f"00000000-0000-0000-0000-7{seq:011d}",
        "number": 900 + seq, "ref": ref, "employee_id": U["priya"], "category": "Other",
        "subject": f"{ref} snapshot", "description": "Unassigned snapshot used by the sweep test.",
        "priority": priority, "status": "Open", "assignee_id": None,
        "created_at": _age(hours_old), "updated_at": _age(hours_old),
        "first_reply_at": None, "resolved_at": None, "closed_by": None,
        "attachment_path": None, "attachment_name": None, "attachment_size": None,
    }


def _quieten_seed_sweeps(api):
    """The seeded TKT-101 (Open, unassigned, old) would breach on every sweep —
    park it out of the sweep's Unassigned/Open scope for a clean slate."""
    api.fake.tickets.rows[0]["status"] = "Resolved"


def test_sla_sweep_notifies_once_per_threshold(api):
    _quieten_seed_sweeps(api)
    api.fake.tickets.rows.append(_ticket_row("TKT-900", "Medium", 30, 1))
    api.fake.tickets.rows.append(_ticket_row("TKT-901", "Low", 1, 2))  # fresh -> no breach

    r = api.client.post("/api/notifications/sweep", json={"userId": U["ben"]})
    assert r.status_code == 200 and r.json()["slaNotified"] == 1

    for agent in AGENTS:
        rows = [n for n in list_for(api, agent) if n["ticketRef"] == "TKT-900"]
        assert len(rows) == 1 and rows[0]["type"] == "sla_breached"
        assert rows[0]["payload"]["thresholdHours"] == 24
    assert [n for n in list_for(api, U["ruth"]) if n["ticketRef"] == "TKT-901"] == []
    assert [n for n in list_for(api, U["priya"]) if n["ticketRef"] == "TKT-900"] == []

    # second sweep: ticket/threshold already notified -> no new rows
    assert api.client.post("/api/notifications/sweep", json={"userId": U["ben"]}).json()["slaNotified"] == 0


def test_urgent_threshold_is_shorter(api):
    _quieten_seed_sweeps(api)
    api.fake.tickets.rows.append(_ticket_row("TKT-902", "Urgent", 5, 3))

    r = api.client.post("/api/notifications/sweep", json={"userId": U["ben"]})
    assert r.json()["slaNotified"] == 1
    rows = [n for n in list_for(api, U["alicia"]) if n["ticketRef"] == "TKT-902"]
    assert rows[0]["payload"]["thresholdHours"] == 4


def test_retention_cleanup_deletes_stale_rows(api):
    too_old_read = {
        "id": "00000000-0000-0000-0000-800000000001",
        "recipient_id": U["ben"], "ticket_id": None, "ticket_ref": None,
        "type": "ticket_created", "channel": "in_app", "actor_name": None,
        "payload": {}, "message": "old read copy", "read": True,
        "created_at": _age(24 * 60), "read_at": _age(24 * 30),
    }
    fresh_unread = {
        "id": "00000000-0000-0000-0000-800000000002",
        "recipient_id": U["ben"], "ticket_id": None, "ticket_ref": None,
        "type": "ticket_created", "channel": "in_app", "actor_name": None,
        "payload": {}, "message": "fresh unread", "read": False,
        "created_at": _age(24 * 35), "read_at": None,
    }
    ancient_unread = {
        "id": "00000000-0000-0000-0000-800000000003",
        "recipient_id": U["ben"], "ticket_id": None, "ticket_ref": None,
        "type": "ticket_created", "channel": "in_app", "actor_name": None,
        "payload": {}, "message": "ancient unread", "read": False,
        "created_at": _age(24 * 200), "read_at": None,
    }
    api.fake.notifications.rows.extend([too_old_read, fresh_unread, ancient_unread])

    r = api.client.post("/api/notifications/sweep", json={"userId": U["ben"]})
    assert r.json()["deleted"] == 2

    surviving_ids = {
        n["id"] for n in api.fake.notifications.rows
        if n["id"] in {too_old_read["id"], fresh_unread["id"], ancient_unread["id"]}
    }
    assert surviving_ids == {fresh_unread["id"]}
