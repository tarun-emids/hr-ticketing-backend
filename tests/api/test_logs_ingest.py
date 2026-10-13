"""Frontend log ingestion (POST /api/logs/ingest) — corr. with backend logs.

Runs hermetically: the shared conftest fixture wires the offline database; ingestion
doesn't touch Supabase at all — events go through the standard logging
chain like every backend record (asserted via caplog, LOG_TO_FILE=false).
"""

import logging

_ingest = "/api/logs/ingest"


def _event(**over):
    base = {
        "logId": "0b5b6b7c8d9e4f0a1b2c3d4e5f6a7b8c",
        "correlationId": "3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c",
        "level": "INFO",
        "event": "http_request_start",
        "method": "POST",
        "endpoint": "/api/tickets",
        "occurredAt": "2026-10-09T07:00:00.000Z",
    }
    base.update(over)
    return base


def _post(api, batch):
    res = api.client.post(_ingest, json={"events": batch})
    return res


def test_ingest_accepts_valid_batch_and_logs_through_pipeline(api, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.frontend"):
        res = _post(
            api,
            [_event(), _event(event="http_request_succeeded", statusCode=201, durationMs=512.5)],
        )
    assert res.status_code == 202
    assert res.json() == {"accepted": 2}
    records = [r for r in caplog.records if r.name == "hrdesk.frontend"]
    assert len(records) == 2
    first = records[0]
    assert first.http["correlation_id"] == _event()["correlationId"]
    assert first.http["source"] == "frontend"
    assert first.http["path"] == "/api/tickets"
    assert first.getMessage().startswith("[frontend] http_request_start")
    assert first.getMessage().endswith("POST /api/tickets")


def test_ingest_rejects_oversized_batch_and_bad_fields(api):
    too_big = _post(api, [_event() for _ in range(21)])
    assert too_big.status_code == 422

    bad_id = _post(api, [_event(correlationId="bad|injecting")])
    assert bad_id.status_code == 422

    bad_level = _post(api, [_event(level="TRACE")])
    assert bad_level.status_code == 422

    bad_status = _post(api, [_event(statusCode=999)])
    assert bad_status.status_code == 422


def test_ingest_is_rate_limited_per_client(api, monkeypatch):
    import time

    from app.services import log_ingest_service as svc_mod

    monkeypatch.setattr(svc_mod.time, "monotonic", time.monotonic)
    hits = svc_mod._RATE_HITS.setdefault("testclient", [])
    hits.clear()
    for _ in range(svc_mod.RATE_LIMIT_REQUESTS_PER_MINUTE):
        hits.append(svc_mod.time.monotonic())
    flooded = _post(api, [_event()])
    assert flooded.status_code == 429
    hits.clear()  # window passes → allowed again
    ok = _post(api, [_event()])
    assert ok.status_code == 202


def test_ingest_never_breaks_ticket_creation(api, monkeypatch):
    """Sink failure is swallowed server-side; ticket flow keeps working."""
    from app.services.log_ingest_service import LogIngestService

    monkeypatch.setattr(LogIngestService, "ingest", lambda self, payload: 1 / 0)
    failing = _post(api, [_event()])
    assert failing.status_code == 202
    assert failing.json() == {"accepted": 0}

    employee = api.client.get("/api/users").json()[0]
    created = api.client.post(
        "/api/tickets",
        json={
            "employeeId": employee["id"],
            "category": "Payroll",
            "priority": "High",
            "subject": "Logging must not break tickets",
            "description": "Ingestion failure should leave the API fully functional for creating tickets.",
        },
    )
    assert created.status_code == 201
