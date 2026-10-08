"""Pure notification rules: recipients, thresholds, message content."""
from app.services.notification_service import (
    EV_SLA,
    assigned_recipients,
    build_row,
    created_recipients,
    reply_recipients,
    sla_threshold_hours,
    status_recipients,
)

from tests.conftest import U

AGENTS = [U["alicia"], U["ben"], U["ruth"]]


def test_created_informs_all_agents():
    assert created_recipients(AGENTS) == AGENTS


def test_assignment_recipients():
    assert assigned_recipients(U["ben"], None) == [U["ben"]]
    # actor would be excluded, but manual PATCH/assignee carries no actor here
    assert assigned_recipients(None, U["ben"]) == []
    assert assigned_recipients(U["ben"], U["ben"]) == []


def test_status_change_excludes_actor():
    got = status_recipients(U["priya"], U["ben"], U["ben"])
    assert U["priya"] in got
    assert U["ben"] not in got


def test_status_change_informs_owner_and_assignee():
    got = status_recipients(U["priya"], U["ben"], U["ruth"])
    assert set(got) == {U["priya"], U["ben"]}


def test_reply_rules():
    # agent replies on an assigned ticket -> owner only (author excluded)
    got = reply_recipients(U["marcus"], U["alicia"], U["alicia"], "agent", AGENTS)
    assert got == [U["marcus"]]
    # employee replies on an assigned ticket -> assignee only
    got = reply_recipients(U["marcus"], U["alicia"], U["marcus"], "employee", AGENTS)
    assert got == [U["alicia"]]
    # employee replies on an UNASSIGNED ticket -> fan out to agents
    got = reply_recipients(U["marcus"], None, U["marcus"], "employee", AGENTS)
    assert set(got) == set(AGENTS)
    # agent replies on an unassigned ticket -> owner only
    got = reply_recipients(U["marcus"], None, U["alicia"], "agent", AGENTS)
    assert got == [U["marcus"]]


def test_sla_thresholds():
    assert sla_threshold_hours("Urgent") == 4
    assert sla_threshold_hours("High") == 24
    assert sla_threshold_hours("Medium") == 24
    assert sla_threshold_hours("Low") == 24
    assert sla_threshold_hours("anything") == 24


def test_message_never_carries_ticket_content():
    """HR tickets are sensitive: subject/description must never appear in a
    notification row — creator passes only shallow fields anyway, and this
    pins that the message is generic even if the ticket dict is full."""
    ticket = {
        "id": "traits-uuid",
        "ref": "TKT-101",
        "category": "Payroll",
        "subject": "Payslip mentions confidential bonus dispute",
        "description": "Very private complaint details should stay out of notifications",
    }
    row = build_row(U["alicia"], ticket, EV_SLA, None, {"thresholdHours": 24})
    assert row["message"] == "TKT-101 is still unassigned after 24 hours"
    assert row["message"] != ticket["subject"]
    assert "confidential" not in json_dumps(row)


def json_dumps(row: dict) -> str:
    import json

    return json.dumps(row, default=str)
