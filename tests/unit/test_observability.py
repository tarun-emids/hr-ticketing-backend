"""Observability: structured logging, trace correlation, request ids, files.

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
    _current_span_ids,
    background_span,
    db_span,
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


def _record(msg, level=logging.INFO, exc_info=None, http=None):
    rec = logging.LogRecord(
        "hrdesk.request",
        level,
        "path/to/tests.py",
        1,
        msg,
        None,
        exc_info,
        func=None,
        sinfo=None,
    )
    if http is not None:
        rec.http = http  # mirror logging.info(msg, extra={"http": ...})
    return rec


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


def test_query_strings_never_reach_middleware_logs(id_app, caplog):
    """The middleware's own record carries the path only — never the query."""
    with caplog.at_level(logging.INFO, logger="hrdesk.request"):
        res = id_app.client.get("/ping?access_token=sekrit-token-zzz&q=1")
    assert res.status_code == 200
    rec = _request_log_records(caplog)[0]
    assert rec.http["path"] == "/ping"  # path only, never query
    assert "sekrit-token-zzz" not in JsonLogFormatter().format(rec)
    assert "sekrit-token-zzz" not in ConsoleLogFormatter().format(rec)


def test_sensitive_query_params_redacted_in_emitted_output(id_app, caplog):
    """httpx logs full request URLs — sensitive values must still be masked in
    what we EMIT (formatter-level redaction covers third-party lines too)."""
    with caplog.at_level(logging.INFO):
        res = id_app.client.get("/ping?access_token=sekrit-token-zzz&q=1")
    assert res.status_code == 200
    httpx_records = [r for r in caplog.records if r.name == "httpx"]
    assert httpx_records, "the httpx URL line should be captured raw"
    rec = httpx_records[0]

    for formatted in (JsonLogFormatter().format(rec), ConsoleLogFormatter().format(rec)):
        assert "access_token=[REDACTED]" in formatted  # param name retained
        assert "sekrit-token-zzz" not in formatted  # value masked


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
