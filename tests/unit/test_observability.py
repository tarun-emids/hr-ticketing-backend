"""Observability: structured logging, trace correlation, request ids, files,
and the flow_operation event trio.

Runs fully offline: the conftest sets TRACE_ENABLED=false and LOG_TO_FILE=false
so app.main never creates the OTLP exporter or repo log files, and this module
attaches an InMemorySpanExporter instead. No network, no Jaeger.

Requires the opentelemetry packages (added to requirements.txt together with
this file — installing requirements.txt is a prerequisite of the suite).
"""

import json
import logging
import re
import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import context as otel_context
from opentelemetry import trace as otel_trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from psycopg.errors import ForeignKeyViolation

from app import config as app_config
from app.observability import (
    ConsoleLogFormatter,
    JsonLogFormatter,
    RequestLogMiddleware,
    _ExportErrorRateFilter,
    _current_span_ids,
    background_span,
    db_span,
    flow_event,
    flow_operation,
    flow_warning,
    new_run_id,
    setup_logging,
    setup_tracing,
)
from app.repositories.base import run

TRACE_ID_HEX = "0123456789abcdef0123456789abcdef"
PARENT_SPAN_HEX = "89abcdef00112233"
UUID_RE = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


@pytest.fixture(scope="module", autouse=True)
def _global_provider():
    """One SDK TracerProvider + InMemory exporter for this module.

    conftest keeps TRACE_ENABLED=false, so app.main never installs its own
    global provider — this fixture owns the module's spans (set once per
    process; OpenTelemetry ignores later set_tracer_provider calls).
    """
    if type(otel_trace.get_tracer_provider()).__name__ != "ProxyTracerProvider":
        pytest.skip(
            "a global TracerProvider is already installed; span assertions would not be inspectable"
        )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    otel_trace.set_tracer_provider(provider)
    yield exporter
    exporter.clear()


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------

def _record(msg, level=logging.INFO, exc_info=None, http=None, name="hrdesk.request"):
    rec = logging.LogRecord(
        name, level, "path/to/tests.py", 1, msg, None, exc_info,
        func=None, sinfo=None,
    )
    if http is not None:
        rec.http = http  # mirror logging.info(msg, extra={"http": ...})
    return rec


def _flow_records(caplog):
    return [r for r in caplog.records if r.name == "hrdesk.flow"]


def test_json_log_basic_fields():
    rec = _record(
        "GET /t -> 200",
        http={"method": "GET", "path": "/t", "status": 200, "duration_ms": 3.2},
    )
    payload = json.loads(JsonLogFormatter().format(rec))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "hrdesk.request"
    assert payload["message"] == "GET /t -> 200"
    assert payload["method"] == "GET"
    assert payload["path"] == "/t"
    assert payload["status"] == 200
    assert payload["duration_ms"] == 3.2
    assert "ts" in payload
    assert "trace_id" not in payload  # no active span in this test
    assert re.fullmatch(r"[0-9a-f]{32}", payload["log_id"])  # per-record id


def test_json_log_carries_exception_payload():
    try:
        raise ValueError("boom")
    except ValueError:
        rec = _record("bad request", exc_info=sys.exc_info())
    payload = json.loads(JsonLogFormatter().format(rec))
    assert payload["exception_type"] == "ValueError"
    assert 'raise ValueError("boom")' in payload["exc"]


def test_console_log_format_shape():
    line = ConsoleLogFormatter().format(_record("plain message"))
    assert "INFO " in line
    assert "hrdesk.request plain message" in line
    assert "trace=" not in line  # no active span
    assert "req=" not in line  # no request context


def test_log_records_carry_trace_ids_inside_a_span():
    tracer = TracerProvider().get_tracer("tests")
    span = tracer.start_span("unit-test-span")
    token = otel_context.attach(otel_trace.set_span_in_context(span))
    try:
        trace_id, span_id = _current_span_ids()
        ctx = span.get_span_context()
        assert f"{trace_id:032x}" == f"{ctx.trace_id:032x}"
        assert f"{span_id:016x}" == f"{ctx.span_id:016x}"

        payload = json.loads(JsonLogFormatter().format(_record("inside request span")))
        assert payload["trace_id"] == f"{ctx.trace_id:032x}"
        assert payload["span_id"] == f"{ctx.span_id:016x}"

        console_line = ConsoleLogFormatter().format(_record("inside request span"))
        assert f"trace={f'{ctx.trace_id:032x}'}" in console_line
    finally:
        otel_context.detach(token)
        span.end()


def test_json_explicit_http_trace_fields_win_over_context():
    """Ingest events carry the ORIGINAL operation's trace pair; the http extra
    must win so a record never mixes the ingest hop's trace with the original.
    """
    tracer = TracerProvider().get_tracer("tests")
    span = tracer.start_span("ingest-hop-span")
    token = otel_context.attach(otel_trace.set_span_in_context(span))
    try:
        rec = _record(
            "[frontend] http_request_start",
            http={
                "source": "frontend",
                "correlation_id": "req-1234567890",
                "trace_id": "a" * 32,          # original browser operation trace
                "span_id": "b" * 16,
            },
        )
        payload = json.loads(JsonLogFormatter().format(rec))
        assert payload["trace_id"] == "a" * 32
        assert payload["span_id"] == "b" * 16
        assert payload["correlation_id"] == "req-1234567890"
    finally:
        otel_context.detach(token)
        span.end()


# ---------------------------------------------------------------------------
# Sensitive-data policy: query strings never reach emitted output
# ---------------------------------------------------------------------------

def test_url_query_strings_are_stripped_from_emitted_lines():
    """httpx-style lines include the FULL request URL — everything after '?'
    must be gone, while the path (and precious correlation metadata) remains.
    (The JSON formatter escapes embedded quotes, so assert the status token
    without its quotes.)
    """
    line = (
        'HTTP Request: GET https://example.supabase.co/rest/v1/users'
        '?select=*&id=eq.00000000-0000-0000-0000-000000000001&limit=1 "HTTP/2 200 OK"'
    )
    rec = _record(line, name="httpx")
    for formatted in (JsonLogFormatter().format(rec), ConsoleLogFormatter().format(rec)):
        assert "?select" not in formatted               # no query string at all
        assert "id=eq.00000000" not in formatted        # selector value gone
        assert "00000000-0000-0000-0000-000000000001" not in formatted
        assert "https://example.supabase.co/rest/v1/users" in formatted  # path kept
        assert "HTTP/2 200 OK" in formatted             # status metadata kept


def test_sensitive_query_params_redacted_in_emitted_output():
    """Denylist masking still applies to non-URL ``name=value`` text (the
    formatter-level redaction covers any emitter, including third parties)."""
    rec = _record("login failed for user with password=s3cr3t-value")
    for formatted in (JsonLogFormatter().format(rec), ConsoleLogFormatter().format(rec)):
        assert "password=[REDACTED]" in formatted
        assert "s3cr3t-value" not in formatted


def test_api_query_params_never_reach_middleware_logs(id_app, caplog):
    """The middleware's own record carries the path only — never the query."""
    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        res = id_app.client.get("/ping?employeeId=00000000-0000-0000-0000-000000000009&q=1")
    assert res.status_code == 200
    rec = _request_log_records(caplog)[0]
    assert rec.http["path"] == "/ping"                    # path only, never query
    formatted = JsonLogFormatter().format(rec)
    assert "employeeId=" not in formatted                 # filter value gone
    assert "00000000-0000-0000-0000-000000000009" not in formatted


def test_httpx_supabase_urls_sanitized_end_to_end(caplog):
    """The raw httpx URL line enters the pipeline unsanitized (httpx logs the
    full URL) — what we EMIT must carry the path only, no query/id values."""
    supabase_line = (
        'HTTP Request: GET https://x.supabase.co/rest/v1/tickets'
        '?select=*&employee_id=eq.985c8483-044c-4bdd-86d6-11c8731f089c&order=updated_at.desc "HTTP/2 200"'
    )
    with caplog.at_level(logging.INFO, logger="httpx"):
        logging.getLogger("httpx").info(supabase_line)
    rec = [r for r in caplog.records if r.name == "httpx"][0]
    formatted = JsonLogFormatter().format(rec)
    assert "employee_id=" not in formatted
    assert "985c8483-044c-4bdd-86d6-11c8731f089c" not in formatted
    assert "?select" not in formatted
    assert "/rest/v1/tickets" in formatted


def test_exception_payloads_are_redacted_too():
    """Exception args/tracebacks may embed URLs (httpx/httpcore errors) — the
    exc text must go through the same redaction."""
    try:
        raise RuntimeError("connect failed for https://x.supabase.co/rest/v1/users?token=abc123")
    except RuntimeError:
        rec = _record("store failure", exc_info=sys.exc_info())
    payload = json.loads(JsonLogFormatter().format(rec))
    assert "token=abc123" not in payload["exc"]
    assert "https://x.supabase.co/rest/v1/users?token=abc123" not in payload["exc"]


# ---------------------------------------------------------------------------
# Layer events: flow_event / flow_operation / flow_warning
# ---------------------------------------------------------------------------

def test_flow_event_carries_event_operation_and_stamps_context(caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        flow_event(
            "ticket.repository.insert_started",
            operation="tickets.create",
            table="tickets",
        )
    rec = _flow_records(caplog)[0]
    assert rec.getMessage() == "ticket.repository.insert_started"
    assert rec.http["source"] == "backend"
    assert rec.http["event"] == "ticket.repository.insert_started"
    assert rec.http["operation"] == "tickets.create"
    assert rec.http["table"] == "tickets"
    payload = json.loads(JsonLogFormatter().format(rec))
    assert payload["event"] == "ticket.repository.insert_started"
    assert payload["operation"] == "tickets.create"


def test_flow_operation_emits_started_completed_without_records_leaks(caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        with flow_operation("tickets.get", operation="tickets.get",
                            method="GET", path="/api/tickets/TKT-1") as op:
            op["ticket_ref"] = "TKT-1"

    events = _flow_records(caplog)
    assert [r.http["event"] for r in events] == ["tickets.get.started", "tickets.get.completed"]
    assert all(r.http["operation"] == "tickets.get" for r in events)
    completed = events[1]
    assert completed.http["ticket_ref"] == "TKT-1"
    assert re.fullmatch(r"\d+(\.\d+)?", str(completed.http["duration_ms"]))
    assert "request_id" not in completed.http  # no request context here (unit scope)


def test_flow_operation_failed_classifies_http_status(caplog):
    class _DomainError(Exception):
        status_code = 422

    with caplog.at_level(logging.INFO, logger="hrdesk.flow"):
        with pytest.raises(_DomainError):
            with flow_operation("drafts.submit", operation="drafts.submit",
                                method="POST", path="/api/drafts/abc/submit"):
                raise _DomainError("nope")

    events = _flow_records(caplog)
    assert [r.http["event"] for r in events] == ["drafts.submit.started", "drafts.submit.failed"]
    failed = events[1]
    assert failed.http["status"] == 422
    assert failed.http["error"] == "_DomainError"     # safe class name only
    assert "nope" not in failed.getMessage()          # message text never in the event


def test_flow_operation_unexpected_error_has_no_status(caplog):
    with pytest.raises(RuntimeError):
        with flow_operation("users.list", operation="users.list"):
            raise RuntimeError("exploded")

    failed = _flow_records(caplog)[1]
    assert failed.http["event"] == "users.list.failed"
    assert "status" not in failed.http            # nothing invented
    assert failed.http["error"] == "RuntimeError"


def test_flow_warning_emits_at_warning_level(caplog):
    with caplog.at_level(logging.WARNING, logger="hrdesk.flow"):
        flow_warning("logs.ingest.rejected", operation="logs.ingest", limit_per_minute=60)
    rec = _flow_records(caplog)[0]
    assert rec.levelname == "WARNING"
    assert rec.http["event"] == "logs.ingest.rejected"
    assert rec.http["limit_per_minute"] == 60


def test_new_run_id_shape():
    for _ in range(3):
        assert re.fullmatch(r"[0-9a-f]{32}", new_run_id())


# ---------------------------------------------------------------------------
# db_span helper + repository error mapping (behavior must be preserved)
# ---------------------------------------------------------------------------


class _Res:
    pass


class FakeSelectBuilder:
    @contextmanager
    def connection(self):
        yield self


class _FailingBuilder(FakeSelectBuilder):
    def execute(self, _sql, _params):
        raise ForeignKeyViolation("fk violated")


def test_db_span_creates_recording_span_with_attributes():
    with db_span("db.postgresql.tickets.select", {"db.operation": "select"}) as span:
        assert span is not None
        assert span.is_recording()
        assert span.name == "db.postgresql.tickets.select"


def test_run_maps_postgresql_errors():
    with pytest.raises(Exception) as err:
        run(_FailingBuilder(), "INSERT INTO users (id) VALUES (%s)", ("id",), table="users")
    assert "Database rejected the write" in str(err.value)


def test_background_span_returns_recording_span():
    with background_span("hrdesk.jobs.sla_sweep") as span:
        assert span is not None and span.is_recording()


# ---------------------------------------------------------------------------
# setup_tracing switch + W3C traceparent extraction
# ---------------------------------------------------------------------------


def test_setup_tracing_disabled_is_a_clean_noop(monkeypatch):
    monkeypatch.setattr(app_config, "TRACE_ENABLED", False)
    assert setup_tracing(FastAPI()) is False


@pytest.fixture()
def client_with_spans():
    """A tiny wired FastAPI app capturing in-span context + finished spans.

    Instrumenting this test-local app (not app.main) keeps the assertion
    surface inspectable while exercising the same FastAPIInstrumentor path
    the real backend startup uses.
    """
    captured = {}

    app = FastAPI()

    @app.get("/traced", include_in_schema=False)
    def traced():
        span = otel_trace.get_current_span()
        captured["trace_id"] = span.get_span_context().trace_id
        return {"ok": True}

    @app.get("/health", include_in_schema=False)
    def health():
        return {"ok": True}

    FastAPIInstrumentor.instrument_app(app)
    yield SimpleNamespace(client=TestClient(app), captured=captured)


def test_traceparent_from_client_joins_server_span(client_with_spans):
    stub = client_with_spans
    headers = {"traceparent": f"00-{TRACE_ID_HEX}-{PARENT_SPAN_HEX}-01"}
    res = stub.client.get("/traced", headers=headers)
    assert res.status_code == 200
    # business code ran inside a span of the browser's trace
    assert f"{stub.captured['trace_id']:032x}" == TRACE_ID_HEX


def test_untraced_request_starts_its_own_trace(client_with_spans):
    stub = client_with_spans
    res = stub.client.get("/traced")
    assert res.status_code == 200
    assert stub.captured["trace_id"] not in (None, 0)


# ---------------------------------------------------------------------------
# Request log middleware
# ---------------------------------------------------------------------------


def test_request_log_middleware_outputs_one_record_per_request(caplog):
    app = FastAPI()

    @app.get("/ping", include_in_schema=False)
    def ping():
        return {"ok": True}

    app.add_middleware(RequestLogMiddleware)
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        res = client.get("/ping")
    assert res.status_code == 200
    lines = [r for r in caplog.records if r.name == "hrdesk.request"]
    assert len(lines) == 1
    rec = lines[0]
    assert rec.getMessage().startswith("GET /ping -> 200")
    assert rec.http["method"] == "GET"
    assert rec.http["path"] == "/ping"
    assert rec.http["status"] == 200
    assert rec.http["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# Request IDs: X-Request-ID header, validation, logging
# ---------------------------------------------------------------------------


@pytest.fixture()
def id_app():
    app = FastAPI()

    @app.get("/ping", include_in_schema=False)
    def ping():
        return {"ok": True}

    @app.get("/health", include_in_schema=False)
    def health():
        return {"ok": True}

    app.add_middleware(RequestLogMiddleware)
    return SimpleNamespace(client=TestClient(app))


def _request_log_records(caplog):
    return [r for r in caplog.records if r.name == "hrdesk.request"]


def test_request_id_generated_returned_and_logged(id_app, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        res = id_app.client.get("/ping")
    request_id = res.headers["x-request-id"]
    assert re.fullmatch(UUID_RE, request_id)  # generated: standard UUID
    records = _request_log_records(caplog)
    assert len(records) == 1
    assert records[0].http["request_id"] == request_id  # header agrees with log


def test_health_and_preflight_get_ids_without_log_noise(id_app, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        health = id_app.client.get("/health")
        preflight = id_app.client.options("/ping")
    assert re.fullmatch(UUID_RE, health.headers["x-request-id"])
    assert re.fullmatch(UUID_RE, preflight.headers["x-request-id"])
    assert _request_log_records(caplog) == []  # ids, but no log lines


def test_client_supplied_request_id_is_accepted_and_logged(id_app, caplog):
    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        res = id_app.client.get("/ping", headers={"X-Request-ID": "abc-DEF_2026.test"})
    assert res.headers["x-request-id"] == "abc-DEF_2026.test"
    assert _request_log_records(caplog)[0].http["request_id"] == "abc-DEF_2026.test"


def test_invalid_client_request_ids_are_replaced_safely(id_app):
    bad_ids = (
        "short",  # < 8 chars
        "has space",  # whitespace
        "bad|pipe",  # injection-ish character
        "x" * 100,  # length abuse
        "",  # empty
        "tab\tchar",  # control character
        "{log-forgery}",  # braces/quotes
    )
    for bad in bad_ids:
        res = id_app.client.get("/ping", headers={"X-Request-ID": bad})
        request_id = res.headers["x-request-id"]
        assert re.fullmatch(UUID_RE, request_id)  # regenerated, not echoed
        assert request_id != bad


def test_separate_requests_get_different_generated_ids(id_app):
    first = id_app.client.get("/ping").headers["x-request-id"]
    second = id_app.client.get("/ping").headers["x-request-id"]
    assert first != second
    assert re.fullmatch(UUID_RE, first) and re.fullmatch(UUID_RE, second)


def test_request_log_carries_request_trace_and_span_ids(caplog):
    """Integration check: middleware id + OTel server span ids in ONE record."""
    app = FastAPI()

    @app.get("/traced", include_in_schema=False)
    def traced():
        return {"ok": True}

    app.add_middleware(RequestLogMiddleware)
    FastAPIInstrumentor.instrument_app(app)
    client = TestClient(app)

    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        res = client.get(
            "/traced", headers={"traceparent": f"00-{TRACE_ID_HEX}-{PARENT_SPAN_HEX}-01"}
        )
    rec = _request_log_records(caplog)[0]
    assert rec.http["request_id"] == res.headers["x-request-id"]
    assert rec.http["trace_id"] == TRACE_ID_HEX  # joins the browser trace
    assert re.fullmatch(r"[0-9a-f]{16}", rec.http["span_id"])  # server span's own id


# ---------------------------------------------------------------------------
# OTLP exporter log throttle (collector down must not flood the log)
# ---------------------------------------------------------------------------

def test_export_throttle_disabled_lets_everything_through():
    flt = _ExportErrorRateFilter(0)
    assert all(flt.filter(_record("m")) for _ in range(5))


def test_export_throttle_passes_first_then_collapses_a_window(caplog):
    flt = _ExportErrorRateFilter(60)
    assert flt.filter(_record("first failure")) is True    # visible
    assert flt.filter(_record("second")) is False          # collapsed
    assert flt.filter(_record("third")) is False

    # Window elapsed (simulate) — the next failure summary + line pass.
    with caplog.at_level(logging.WARNING, logger="hrdesk"):
        flt._last_pass = time.monotonic() - 61
        assert flt.filter(_record("post-window")) is True
    summaries = [r for r in caplog.records if r.name == "hrdesk"]
    assert any("2 exporter log lines suppressed" in r.getMessage() for r in summaries)


def test_export_throttle_quiet_after_recovery():
    """No failures -> no drop count -> next window opens without a summary."""
    flt = _ExportErrorRateFilter(60)
    assert flt.filter(_record("a")) is True
    assert flt._dropped == 0    # nothing was collapsed


# ---------------------------------------------------------------------------
# Persistent log files (rotation sink) + fail-safe behavior
# ---------------------------------------------------------------------------


def _reset_handlers_to_default(monkeypatch):
    monkeypatch.setattr(app_config, "LOG_TO_FILE", False)
    setup_logging()


def test_logs_persist_and_survive_restart(tmp_path, monkeypatch):
    log_file = tmp_path / "app.log"
    monkeypatch.setattr(app_config, "LOG_TO_FILE", True)
    monkeypatch.setattr(app_config, "LOG_FILE_PATH", str(log_file))

    setup_logging()  # boot-equivalent: console + rotating file handler
    logging.getLogger("hrdesk.request").info("before restart")

    setup_logging()  # simulated backend restart (handler rebuild)
    logging.getLogger("hrdesk.request").info("after restart")

    try:
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # the file survived the "restart" (append kept)
        payloads = [json.loads(line) for line in lines]
        assert [p["message"] for p in payloads] == ["before restart", "after restart"]
        assert payloads[0]["log_id"] != payloads[1]["log_id"]  # unique per record
        for payload in payloads:
            assert re.fullmatch(r"[0-9a-f]{32}", payload["log_id"])
            assert payload["service_name"] == app_config.OTEL_SERVICE_NAME
            assert "ts" in payload and "level" in payload
    finally:
        _reset_handlers_to_default(monkeypatch)


def test_unwritable_file_sink_never_breaks_requests(id_app, monkeypatch):
    """A broken sink must not take request handling down (fail-safe policy)."""
    monkeypatch.setattr(app_config, "LOG_TO_FILE", True)
    monkeypatch.setattr(app_config, "LOG_FILE_PATH", "/dev/null/not-a-dir/app.log")
    setup_logging()
    try:
        for _ in range(3):
            res = id_app.client.get("/ping")  # emit-time failures are trapped by logging
            assert res.status_code == 200
    finally:
        _reset_handlers_to_default(monkeypatch)
