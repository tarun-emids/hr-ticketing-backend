"""Ticket-create flow events — controller → service → repository layers.

The layered events must appear in execution order under ``hrdesk.flow`` with
one shared ``request_id`` (the validated client X-Request-ID), an operation
tag, and NO ticket content (subject/description) anywhere in a record.
Runs hermetically: FakeSupabase via the shared conftest; no network.

Every operation in the app now emits flow events, so tests scope their
assertions to the records of THEIR request (by request_id) — lookups like
GET /api/users that precede the tested action legitimately emit their own.
"""
import json
import logging
import re

from app.observability import JsonLogFormatter

SUBJECT = "End to end flow events ticket"
DESCRIPTION = "Posting this ticket should emit the full layer event chain for the flow."


def _flow_records(caplog, request_id=None):
    records = [r for r in caplog.records if r.name == "hrdesk.flow"]
    if request_id is not None:
        formatted = [json.loads(JsonLogFormatter().format(r)) for r in records]
        records = [rec for rec, payload in zip(records, formatted)
                   if payload.get("request_id") == request_id]
    return records


def _event_names(records):
    return [r.http["event"] for r in records]


def test_ticket_create_flow_emits_layer_events_in_order(api, caplog):
    employee = api.client.get("/api/users").json()[0]

    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.post(
            "/api/tickets",
            headers={"X-Request-ID": "flow-e2e-request001"},
            json={
                "employeeId": employee["id"],
                "category": "Payroll",
                "priority": "High",
                "subject": SUBJECT,
                "description": DESCRIPTION,
            },
        )

    assert res.status_code == 201

    mine = _flow_records(caplog, "flow-e2e-request001")
    names = _event_names(mine)
    assert names == [
        "tickets.create.started",
        "ticket.service.validation_completed",
        "ticket.repository.insert_started",
        "ticket.repository.insert_completed",
        "notification.deliver.started",
        "notification.deliver.completed",
        "tickets.create.completed",
    ]

    for rec in mine:
        assert rec.http["request_id"] == "flow-e2e-request001"  # one id across layers

    started = mine[0]
    assert started.http["operation"] == "tickets.create"
    assert started.http["source"] == "backend"
    assert started.http["method"] == "POST"
    assert started.http["path"] == "/api/tickets"

    completed = mine[-1]
    assert completed.http["ticket_ref"] == res.json()["id"]
    assert completed.http["status"] == "created"
    assert re.fullmatch(r"\d+(\.\d+)?", str(completed.http["duration_ms"]))

    validation = mine[1]
    assert validation.http["employee_id"] == employee["id"]
    assert validation.http["category"] == "Payroll"
    assert validation.http["priority"] == "High"

    insert = mine[3]
    assert insert.http["table"] == "tickets"
    assert insert.http["ticket_ref"] == res.json()["id"]

    deliver_started = mine[4]
    assert deliver_started.http["event_type"] == "ticket_created"  # event TYPE, safe
    assert deliver_started.http["recipient_count"] >= 1

    deliver_completed = mine[5]
    assert deliver_completed.http["event"] == "notification.deliver.completed"
    assert deliver_completed.http["delivered"] >= 1  # agents were notified


def test_ticket_create_rejected_flow_logs_controller_failed(api, caplog):
    """Validation failure: started → failed (422); service/repository layers
    are never reached."""
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.post(
            "/api/tickets",
            headers={"X-Request-ID": "flow-e2e-fail-0001"},
            json={
                "employeeId": "00000000-0000-0000-0000-000000000099",
                "category": "Payroll",
                "priority": "High",
                "subject": SUBJECT,
                "description": DESCRIPTION,
            },
        )

    assert res.status_code == 422
    records = _flow_records(caplog, "flow-e2e-fail-0001")
    assert _event_names(records) == [
        "tickets.create.started",
        "tickets.create.failed",
    ]
    assert records[1].http["status"] == 422
    assert records[1].http["error"] == "HTTPException"
    assert records[1].http["request_id"] == "flow-e2e-fail-0001"


def test_flow_events_and_middleware_share_the_request_id(api, caplog):
    """Middleware line and layer events correlate on the SAME request id."""
    employee = api.client.get("/api/users").json()[0]
    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        api.client.post(
            "/api/tickets",
            headers={"X-Request-ID": "flow-e2e-shared-01"},
            json={
                "employeeId": employee["id"],
                "category": "Leave",
                "priority": "Medium",
                "subject": SUBJECT,
                "description": DESCRIPTION,
            },
        )

    # caplog spans the whole test (the users lookup above also logs) — scope
    # the comparison to the POST's own middleware record.
    request_lines = [
        r for r in caplog.records
        if r.name == "hrdesk.request"
        and r.http["path"] == "/api/tickets"
        and r.http["method"] == "POST"
    ]
    ids = {r.http["request_id"] for r in request_lines}
    assert len(request_lines) == 1
    assert ids == {"flow-e2e-shared-01"}


def test_flow_events_never_carry_ticket_content(api, caplog):
    """No subject/description text may appear in any flow record (HR data) —
    checked across EVERY flow record in the capture, not only this request."""
    employee = api.client.get("/api/users").json()[0]
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        api.client.post(
            "/api/tickets",
            headers={"X-Request-ID": "flow-e2e-nocontent1"},
            json={
                "employeeId": employee["id"],
                "category": "Payroll",
                "priority": "Medium",
                "subject": SUBJECT,
                "description": DESCRIPTION,
            },
        )
    for rec in _flow_records(caplog):
        assert SUBJECT not in rec.getMessage()
        assert DESCRIPTION not in rec.getMessage()
