"""Application-wide flow-event coverage: every operation group emits its
started/completed/failed trio under ``hrdesk.flow`` with the shared request
id, safe error classification, and never any HR-sensitive content.

Offline everywhere: SQLite-backed double (shared conftest), password
verification monkeypatched
at the module boundary (no network, no tokens), storage handled by FakeStorage.
"""

import logging
import re

from tests.conftest import U

SUBJECT = "App wide coverage subject"
DESCRIPTION = "This description text must never appear inside any emitted flow record."


def _flow_records(caplog):
    return [r for r in caplog.records if r.name == "hrdesk.flow"]


def _names(records):
    return [r.http["event"] for r in records]


# ---------------------------------------------------------------------------
# A. Authentication
# ---------------------------------------------------------------------------


def _verify_stub(password, encoded):
    return True


def test_login_success_emits_operation_events(api, caplog, monkeypatch):
    from app.services import auth_service

    monkeypatch.setattr(auth_service, "verify_password", _verify_stub)
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.post(
            "/api/auth/login",
            headers={"X-Request-ID": "appflow-login-00001"},
            json={"email": "priya@acme.com", "password": "valid-test-password"},
        )
    assert res.status_code == 200
    events = _flow_records(caplog)
    assert _names(events) == ["auth.login.started", "auth.login.completed"]
    for rec in events:
        assert rec.http["request_id"] == "appflow-login-00001"
        assert "priya@acme.com" not in rec.getMessage()
        assert "whatever-never-logged" not in rec.getMessage()
    assert events[-1].http["user_id"] == U["priya"]  # verified account's UUID


def test_login_failure_classification(api, caplog, monkeypatch):
    from app.services import auth_service

    def bad_hash(password, encoded_hash):
        return False  # wrong credentials -> 401 from AuthService

    monkeypatch.setattr(auth_service, "verify_password", bad_hash)
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.post(
            "/api/auth/login",
            headers={"X-Request-ID": "appflow-loginfail1"},
            json={"email": "priya@acme.com", "password": "wrong"},
        )
    assert res.status_code == 401
    events = _flow_records(caplog)
    assert _names(events) == ["auth.login.started", "auth.login.failed"]
    failed = events[1]
    assert failed.http["status"] == 401  # mapped flow failure — safe diagnostic
    assert failed.http["error"] == "HTTPException"
    assert failed.http["request_id"] == "appflow-loginfail1"
    assert "wrong" not in failed.getMessage()
    assert "priya@acme.com" not in failed.getMessage()


# ---------------------------------------------------------------------------
# B. Users
# ---------------------------------------------------------------------------


def test_users_listing_events_with_counts(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        users = api.client.get("/api/users", headers={"X-Request-ID": "appflow-users-00001"})
        agents = api.client.get("/api/users/agents")
        meta = api.client.get("/api/meta")
    assert users.status_code == 200 and agents.status_code == 200 and meta.status_code == 200
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "users.list.started",
        "users.list.completed",
        "users.agents.started",
        "users.agents.completed",
        "users.meta.started",
        "users.meta.completed",
    ]
    assert events[1].http["count"] == 7
    assert events[3].http["count"] == 3


# ---------------------------------------------------------------------------
# C. Ticket reads / filters (search value never logged)
# ---------------------------------------------------------------------------


def test_ticket_list_events_never_log_search_text(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.get(
            "/api/tickets",
            params={"status": "Resolved", "q": "equipment"},  # matches seeded TKT-103
        )
    assert res.status_code == 200
    events = _flow_records(caplog)
    assert _names(events) == ["tickets.list.started", "tickets.list.completed"]
    started, completed = events
    assert started.http["status"] == "Resolved"  # enum filter — allowed
    assert "q" not in started.http  # search value never a field
    assert started.http["search"] is True  # presence only
    assert "equipment" not in started.getMessage()
    assert completed.http["count"] == 1  # seeded TKT-103 is Resolved


def test_ticket_get_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        ok = api.client.get("/api/tickets/TKT-102")
        missing = api.client.get("/api/tickets/TKT-404")
    assert ok.status_code == 200 and missing.status_code == 404
    events = _flow_records(caplog)
    assert _names(events) == [
        "tickets.get.started",
        "tickets.get.completed",
        "tickets.get.started",
        "tickets.get.failed",
    ]
    assert events[1].http["ticket_ref"] == "TKT-102"
    assert events[3].http["status"] == 404


# ---------------------------------------------------------------------------
# D. Ticket lifecycle writes (status / priority / assign / auto-assign)
# ---------------------------------------------------------------------------


def test_status_update_full_chain(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.patch(
            "/api/tickets/TKT-101/status",
            headers={"X-Request-ID": "appflow-status-0001"},
            json={"status": "Resolved", "actorId": U["marcus"]},
        )
    assert res.status_code == 200
    names = _names(_flow_records(caplog))
    assert names == [
        "tickets.status.started",
        "ticket.service.validation_completed",
        "ticket.repository.update_started",
        "ticket.repository.update_completed",
        "notification.deliver.started",
        "notification.deliver.completed",
        "tickets.status.completed",
    ]
    records = _flow_records(caplog)
    validation = records[1]
    assert validation.http["to_status"] == "Resolved"
    update_started = records[2]
    # column NAMES only — "Resolved" also stamps resolved_at
    assert update_started.http["patch_columns"] == ["resolved_at", "status"]
    for rec in records:
        assert rec.http["request_id"] == "appflow-status-0001"
    deliver = records[5]
    assert deliver.http["delivered"] == 1  # the owner (employee) was notified


def test_assign_flow_emits_reply_and_update_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.patch(
            "/api/tickets/TKT-101/assignee",
            json={"assigneeId": U["alicia"]},
        )
    assert res.status_code == 200
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "tickets.assign.started",
        "ticket.service.validation_completed",
        "reply.repository.insert_started",  # the agent pickup reply
        "reply.repository.insert_completed",
        "ticket.repository.update_started",
        "ticket.repository.update_completed",
        "notification.deliver.started",  # actual reassignment → deliver
        "notification.deliver.completed",
        "tickets.assign.completed",
    ]
    insert_started = next(r for r in events if r.http["event"] == "reply.repository.insert_started")
    assert insert_started.http["author_role"] == "agent"
    assert events[-1].http["assignee_id"] == U["alicia"]


def test_reassigning_the_same_agent_does_not_notify(api, caplog):
    """Re-picking the current assignee stays quiet (deliver rows absent)."""
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        first = api.client.patch("/api/tickets/TKT-101/assignee", json={"assigneeId": U["alicia"]})
        second = api.client.patch("/api/tickets/TKT-101/assignee", json={"assigneeId": U["alicia"]})
    assert first.status_code == 200 and second.status_code == 200
    events = _flow_records(caplog)
    # first PATCH: assign (9 rows incl. reply insert + deliver);
    # second PATCH: same agent re-picked → reply/deliver stay quiet
    second_ops = [r for r in events[9:]]
    assert _names(second_ops) == [
        "tickets.assign.started",
        "ticket.service.validation_completed",
        "ticket.repository.update_started",
        "ticket.repository.update_completed",
        "tickets.assign.completed",
    ]


def test_auto_assign_logs_selection_milestone(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.post("/api/tickets/TKT-101/auto-assign")
    assert res.status_code == 200
    events = _flow_records(caplog)
    names = _names(events)
    assert "tickets.auto_assign.started" in names
    assert "ticket.service.assignment_selected" in names
    assert "tickets.auto_assign.completed" in names
    selection = next(r for r in events if r.http["event"] == "ticket.service.assignment_selected")
    routed = res.json()["routedTo"]["id"]
    assert selection.http["routed_to"] == routed
    assert selection.http["candidates"] >= 2  # seeded: 3 agents


def test_priority_update_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.patch("/api/tickets/TKT-101/priority", json={"priority": "Urgent"})
    assert res.status_code == 200
    assert _names(_flow_records(caplog)) == [
        "tickets.priority.started",
        "ticket.repository.update_started",
        "ticket.repository.update_completed",
        "tickets.priority.completed",
    ]


def test_agents_workload_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.get("/api/agents/workload")
    assert res.status_code == 200
    events = _flow_records(caplog)
    assert _names(events) == ["agents.workload.started", "agents.workload.completed"]
    assert events[-1].http["agents"] == 3


# ---------------------------------------------------------------------------
# E. Notifications (unread-count deliberately NOT instrumented — polling)
# ---------------------------------------------------------------------------


def test_unread_count_polls_without_flow_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        res = api.client.get("/api/notifications/unread-count", params={"userId": U["priya"]})
    assert res.status_code == 200
    assert _names(_flow_records(caplog)) == []  # middleware line is the only record


def test_notification_list_and_read_flows(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        listed = api.client.get(
            "/api/notifications",
            params={"userId": U["priya"]},
            headers={"X-Request-ID": "appflow-notif-00001"},
        )
        mark_all = api.client.post("/api/notifications/read-all", json={"userId": U["priya"]})
        unknown_id = "00000000-0000-0000-0000-000000000777"
        mark_one = api.client.post(
            f"/api/notifications/{unknown_id}/read", json={"userId": U["priya"]}
        )
    assert listed.status_code == 200 and mark_all.status_code == 200
    assert mark_one.status_code == 404
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "notifications.list.started",
        "notifications.list.completed",
        "notifications.mark_all_read.started",
        "notifications.mark_all_read.completed",
        "notifications.mark_read.started",
        "notifications.mark_read.failed",
    ]
    list_completed = events[1]
    assert list_completed.http["count"] == 0
    failed = events[-1]
    assert failed.http["status"] == 404
    assert failed.http["notification_id"] == unknown_id
    for rec in events[:2]:
        assert rec.http["request_id"] == "appflow-notif-00001"


# ---------------------------------------------------------------------------
# F. Drafts (create / update / submit / attachments)
# ---------------------------------------------------------------------------


def test_draft_create_update_submit_flow(api, caplog):
    """Three separate HTTP requests → three request ids (verified behavior:
    the middleware scopes ids per request — never invent shared ones)."""
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        created = api.client.post(
            "/api/drafts",
            headers={"X-Request-ID": "appflow-drafts-001"},
            json={
                "employeeId": U["priya"],
                "category": "Payroll",
                "priority": "Medium",
                "subject": "Draft about payroll",
                "description": "Draft description long enough for submission validation.",
            },
        )
        draft_id = created.json()["id"]
        updated = api.client.patch(
            f"/api/drafts/{draft_id}",
            params={"employeeId": U["priya"]},
            json={"subject": "Renamed draft subject"},
        )
        submitted = api.client.post(
            f"/api/drafts/{draft_id}/submit", json={"employeeId": U["priya"]}
        )
    assert created.status_code == 201 and updated.status_code == 200
    assert submitted.status_code == 200
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "drafts.create.started",
        "drafts.create.completed",
        "drafts.update.started",
        "drafts.update.completed",
        "drafts.submit.started",
        "draft.service.validation_completed",
        "ticket.repository.insert_started",
        "ticket.repository.insert_completed",
        "notification.deliver.started",
        "notification.deliver.completed",
        "drafts.submit.completed",
    ]
    # events within the same HTTP request share THAT request's id
    create_ids = {r.http["request_id"] for r in events[0:2]}
    update_ids = {r.http["request_id"] for r in events[2:4]}
    submit_ids = {r.http["request_id"] for r in events[4:]}
    assert create_ids == {"appflow-drafts-001"}
    assert len(update_ids) == 1 and len(submit_ids) == 1
    assert not (create_ids & update_ids) and not (update_ids & submit_ids)
    update_started = events[2]
    assert update_started.http["patch_fields"] == ["subject"]  # field NAMES only
    insert_started = events[6]
    assert insert_started.http["operation"] == "drafts.submit"  # flow tag preserved
    submit_completed = events[-1]
    assert submit_completed.http["ticket_ref"] == submitted.json()["id"]


def test_draft_submit_validation_failure(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        created = api.client.post(
            "/api/drafts",
            json={
                "employeeId": U["priya"],
                "category": "Payroll",
                "priority": "Low",
                "subject": "hi",  # < 5 chars → submit fails validation
                "description": "Short draft body text.",
            },
        )
        draft_id = created.json()["id"]
        res = api.client.post(f"/api/drafts/{draft_id}/submit", json={"employeeId": U["priya"]})
    assert res.status_code == 422
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "drafts.create.started",
        "drafts.create.completed",
        "drafts.submit.started",
        "drafts.submit.failed",
    ]
    failed = events[-1]
    assert failed.http["status"] == 422


# ---------------------------------------------------------------------------
# G. Attachments (ticket + draft): sizes/types logged, never names/URLs
# ---------------------------------------------------------------------------


def test_ticket_attachment_upload_and_url_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        upload = api.client.post(
            "/api/tickets/TKT-102/attachment",
            files={"file": ("employee-payslip.pdf", b"pdf-bytes-here", "application/pdf")},
        )
        url = api.client.get("/api/tickets/TKT-102/attachment")
    assert upload.status_code == 200 and url.status_code == 200
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "attachment.upload.started",
        "attachment.storage.upload_completed",
        "ticket.repository.update_started",
        "ticket.repository.update_completed",
        "attachment.upload.completed",
        "attachment.url.started",
        "attachment.storage.url_signed",
        "attachment.url.completed",
    ]
    started = events[0]
    assert "TKT-102" in started.http["path"]  # ref rides the path on start
    assert started.http["ticket_ref"] == "TKT-102"  # request descriptors on both events
    assert started.http["content_type"] == "application/pdf"
    storage = events[1]
    assert storage.http["storage_path"].startswith("TKT-102/")  # bucket path, no filename
    upload_completed = events[4]
    assert upload_completed.http["ticket_ref"] == "TKT-102"
    for rec in events:
        assert "employee-payslip.pdf" not in rec.getMessage()  # file NAME never logged
        assert "fake.supabase.co" not in rec.getMessage()  # signed URL never logged


def test_draft_attachment_upload_events(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        created = api.client.post(
            "/api/drafts",
            json={
                "employeeId": U["priya"],
                "category": "Payroll",
                "priority": "Low",
                "subject": "Draft with file",
                "description": "Long enough draft body text.",
            },
        )
        draft_id = created.json()["id"]
        upload = api.client.post(
            f"/api/drafts/{draft_id}/attachment",
            params={"employeeId": U["priya"]},
            files={"file": ("notes.txt", b"text", "text/plain")},
        )
        url = api.client.get(
            f"/api/drafts/{draft_id}/attachment", params={"employeeId": U["priya"]}
        )
    assert upload.status_code == 200 and url.status_code == 200
    events = _flow_records(caplog)
    names = _names(events)
    assert "drafts.attachment.upload.started" in names
    assert "attachment.storage.upload_completed" in names
    assert "drafts.attachment.upload.completed" in names
    assert "drafts.attachment.url.completed" in names
    started = next(r for r in events if r.http["event"] == "drafts.attachment.upload.started")
    assert started.http["draft_id"] == draft_id
    assert started.http["size_bytes"] == 4
    assert started.http["content_type"] == "text/plain"
    storage = next(
        r
        for r in events
        if r.http["event"] == "attachment.storage.upload_completed"
        and r.http.get("draft_id") == draft_id
    )
    assert storage.http["size_bytes"] == 4
    for rec in events:
        assert "notes.txt" not in rec.getMessage()
        assert "failed" not in rec.getMessage()


# ---------------------------------------------------------------------------
# H. Log-ingestion rejection (rate limiter) — diagnosable, loop-free
# ---------------------------------------------------------------------------


def test_log_ingest_rate_limit_rejection_event(api, caplog, monkeypatch):
    import time as _time

    from app.services import log_ingest_service as svc_mod

    monkeypatch.setattr(svc_mod.time, "monotonic", _time.monotonic)
    hits = svc_mod._RATE_HITS.setdefault("testclient", [])
    hits.clear()
    for _ in range(svc_mod.RATE_LIMIT_REQUESTS_PER_MINUTE):
        hits.append(svc_mod.time.monotonic())
    event = {
        "logId": "0b5b6b7c8d9e4f0a1b2c3d4e5f6a7b8c",
        "correlationId": "7f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c",
        "level": "INFO",
        "event": "http_request_start",
        "occurredAt": "2026-10-12T00:00:00.000Z",
    }
    res = api.client.post("/api/logs/ingest", json={"events": [event]})
    assert res.status_code == 429
    hits.clear()  # restore the limiter for other tests
    records = _flow_records(caplog)
    assert [r.http["event"] for r in records] == ["logs.ingest.rejected"]
    rejected = records[0]
    assert rejected.http["operation"] == "logs.ingest"
    assert rejected.http["limit_per_minute"] == 60
    assert rejected.levelname == "WARNING"


# ---------------------------------------------------------------------------
# I. Background jobs: run ids, durations, and NO fabricated request context
# ---------------------------------------------------------------------------


def test_background_job_events_have_run_id_and_no_request_id(api, caplog):
    """Calling the jobs directly (as the lifespan scheduler does) must produce
    job.sla_sweep.* / job.retention_cleanup.* rows WITHOUT a request_id —
    jobs have no HTTP context; a run_id identifies the run instead."""
    import json as _json

    from app.observability import JsonLogFormatter
    from app.repositories.notification_repository import NotificationRepository
    from app.repositories.ticket_repository import TicketRepository
    from app.repositories.user_repository import UserRepository
    from app.services.notification_service import NotificationService

    svc = NotificationService(
        NotificationRepository(api.fake),
        UserRepository(api.fake),
        TicketRepository(api.fake),
    )
    # The harness seeds rows ~90 minutes old (kept fresh for the window-based
    # analytics tests); a real desk row accumulates age before the sweep
    # notices it, so age the seeded unassigned Open ticket past its SLA
    # target (24h for Medium) inside this test only.
    api.fake.execute(
        "UPDATE tickets SET created_at ="
        " strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now', '-2 days'),"
        " updated_at = created_at WHERE status = 'Open' AND assignee_id IS NULL"
    )
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        notified = svc.run_sla_sweep()
        deleted = svc.run_retention_cleanup()

    assert notified >= 1  # the aged unassigned Open ticket is past its SLA target
    assert deleted == 0  # fresh rows — nothing past retention cutoffs
    events = _flow_records(caplog)
    names = _names(events)
    assert names == [
        "job.sla_sweep.started",
        "notification.deliver.started",
        "notification.deliver.completed",
        "job.sla_sweep.completed",
        "job.retention_cleanup.started",
        "job.retention_cleanup.completed",
    ]
    sweep_started = events[0]
    run_id = sweep_started.http["run_id"]
    assert re.fullmatch(r"[0-9a-f]{32}", run_id)
    sweep_completed = next(r for r in events if r.http["event"] == "job.sla_sweep.completed")
    assert sweep_completed.http["notified"] == notified
    assert re.fullmatch(r"\d+(\.\d+)?", str(sweep_completed.http["duration_ms"]))
    for rec in events:
        # formatted record must NOT carry a request_id: no HTTP context exists
        payload = _json.loads(JsonLogFormatter().format(rec))
        assert "request_id" not in payload
