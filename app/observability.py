"""Structured logging + OpenTelemetry tracing bootstrap.

Everything here is additive and switches off cleanly:

- ``setup_logging()`` installs the app root handlers: console (console|json
  format) and, when ``LOG_TO_FILE`` is on, a rotating JSON log file.
- Records carry correlation ids: ``request_id`` (per HTTP request, also
  echoed as the ``X-Request-ID`` response header), ``trace_id``/``span_id``
  (the active OpenTelemetry context) and ``log_id`` (per JSON record).
- ``setup_tracing(app)`` wires the OTLP/HTTP exporter and instrumentors.
  ``TRACE_ENABLED=false`` skips ALL of it (no middleware, no exporter).
  If the OpenTelemetry packages are not installed yet, tracing degrades to
  disabled with a warning instead of crashing startup.

What gets a span (when tracing is on):

- every ``/api`` HTTP request: a server span, joined to the browser trace
  via the W3C ``traceparent`` header the frontend client sends;
- every PostgreSQL call that goes through ``app.repositories.base.run()``:
  a semantic db span with the operation and table;
- each background notification job run: a root span per sweep.

Nothing inside PostgreSQL itself is instrumented — spans cover the database
calls this backend makes. Jaeger is the trace viewer;
persistent APPLICATION logs are the rotating JSON files, not Jaeger.

Security: never log header values, secrets, or ticket content (subject,
description, reply text). Query strings are deliberately never logged —
the shared redaction used by BOTH formatters strips the whole query part
of any absolute URL in a record (query strings can carry user ids and
filter values that must not leak) and masks dangerous ``name=value`` pairs
in non-URL text, so third-party lines (httpx logs full request URLs)
and exception tracebacks are covered too, at emit time. Client-supplied
request ids are validated against a strict format and regenerated when
invalid — an attacker cannot inject log content through ``X-Request-ID``.
Attributes allowed in events/spans: ticket ref, status, category,
priority, user UUIDs, counts.

Layer events: ``flow_event(event, operation, **fields)`` emits one
structured record per meaningful business-layer step; ``flow_operation()``
is the standard started/completed/failed trio around a whole operation
(controllers use it for every endpoint; background jobs supply their own
``run_id`` because no HTTP request context exists for them). The event
naming convention is ``{resource}.{action}[.{layer}]_{phase}`` — see
controllers/*, services/*, repositories/ticket_repository.py and the
notification jobs for every live event.

Exporter noise: when the OTLP collector (Jaeger) is not running, the OTLP
exporter logs one line per failed batch. ``_ExportErrorRateFilter``
collapses that to at most one raw line per
``OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS`` (default 300) plus a backend
summary line; the application itself is never affected. Startup and
request handling succeed whether or not a collector is reachable.
"""

import contextvars
import json
import logging
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from app import config as app_config

try:  # opentelemetry-api: present after requirements install; optional at import
    from opentelemetry import trace as _otel_trace

    _OTEL_API = True
except ImportError:  # pragma: no cover — only before deps are installed
    _otel_trace = None
    _OTEL_API = False

LOGGER_NAME = "hrdesk"
REQUEST_LOGGER_NAME = "hrdesk.request"
FLOW_LOGGER_NAME = "hrdesk.flow"

# Response header echoing the request id (lowercase over the wire).
REQUEST_ID_HEADER = "x-request-id"

# Client-supplied request ids must be 8-64 chars, start alphanumeric, and
# contain only [A-Za-z0-9_.-] — no whitespace, no control characters, no
# quotes/braces; anything else is discarded and a fresh UUID is generated.
_CLIENT_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{7,63}$")

# Absolute URLs that carry a query string are cut at the '?' (path alone is
# kept for correlation). httpx logs full third-party request URLs
# round-trip — REST/Storage/Auth filters ride in the query as selectors like
# ``id=eq.<uuid>``, i.e. record references that must not reach the log.
# Applied at emit time in the formatters, so third-party lines and exception
# tracebacks are covered too.
_URL_WITH_QUERY_RE = re.compile(r"https?://[^\s\"'<>]*\?[^\s\"'<>]*", re.IGNORECASE)

# Non-URL ``name=value`` snippets with sensitive names are masked in EVERYTHING
# we emit (console + log files). Denylist parameter names; values may be
# percent-encoded as usual.
_SENSITIVE_PARAM_RE = re.compile(
    r"(?i)(access_?token|api_?key|apikey|secret|token|password|passwd|authorization)"
    r"=[^&\s\"']+"
)


def _strip_url_queries(text: str) -> str:
    """Drop the query part of every absolute URL in the text (path kept)."""
    return _URL_WITH_QUERY_RE.sub(lambda m: m.group(0).split("?", 1)[0], text)


def _redact_sensitive(text: str) -> str:
    """Sanitize emitted text: 1) sensitive ``name=value`` pairs masked,
    2) any absolute URL loses its whole query string (see module docstring)."""
    return _strip_url_queries(_SENSITIVE_PARAM_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", text))


# Per-request correlation context (safe across async request handling).
_request_id_var: contextvars.ContextVar = contextvars.ContextVar("hrdesk_request_id", default=None)


def new_request_id() -> str:
    """Standard UUID used for request ids and (fresh) incoming defaults."""
    return str(uuid.uuid4())


def new_run_id() -> str:
    """Identifier for one background-job run (no HTTP request context exists
    for jobs, so they get a run id instead of — never instead of faking — a
    request id; plain uuid4 hex, same shape log ids/SpanExporters use)."""
    return uuid.uuid4().hex


def resolve_request_id(client_value) -> str:
    """Accept a client-supplied request id only in a strictly safe format.

    Returns the validated id, or a freshly generated UUID. Never echoes
    invalid clients values, so log injection via X-Request-ID is impossible.
    """
    if isinstance(client_value, str):
        candidate = client_value.strip()
        if candidate and _CLIENT_REQUEST_ID_RE.match(candidate):
            return candidate
    return new_request_id()


def get_request_id():
    """The current request's id outside request handling (None)."""
    return _request_id_var.get()


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """App logger — after setup_logging() it is structured and correlation-aware."""
    return logging.getLogger(name)


def flow_event(event: str, operation: str | None = None, **fields) -> None:
    """One structured record for a business-layer step.

    The record message IS the event name; useful fields ride the ``http``
    extra, which the JSON formatter merges into the record:
    ``source=backend`` + ``event`` + ``operation`` + whatever the caller
    passed (duration_ms, method, path, ticket_ref …). ``request_id`` is
    stamped explicitly from the request context (when one exists —
    background jobs have none and that is correct, not a bug);
    ``trace_id``/``span_id`` are stamped by the formatters from the active
    span. Logging must never break the flow it observes, so failures are
    swallowed.
    """
    http = {"source": "backend", "event": event}
    request_id = _request_id_var.get()
    if request_id:
        http["request_id"] = request_id
    if operation:
        http["operation"] = operation
    for key, value in fields.items():
        if value is not None:
            http[key] = value
    try:
        get_logger(FLOW_LOGGER_NAME).log(logging.INFO, event, extra={"http": http})
    except Exception:  # pragma: no cover — events must never break business flow
        pass


def flow_warning(event: str, operation: str | None = None, **fields) -> None:
    """Same structured record as flow_event but at WARNING level (used for
    rejections/throttles that operators should see without being errors)."""
    http = {"source": "backend", "event": event}
    request_id = _request_id_var.get()
    if request_id:
        http["request_id"] = request_id
    if operation:
        http["operation"] = operation
    for key, value in fields.items():
        if value is not None:
            http[key] = value
    try:
        get_logger(FLOW_LOGGER_NAME).log(logging.WARNING, event, extra={"http": http})
    except Exception:  # pragma: no cover — events must never break business flow
        pass


@contextmanager
def flow_operation(
    event_base: str,
    operation: str | None = None,
    method: str | None = None,
    path: str | None = None,
    **fields,
):
    """Standard started/completed/failed event trio around one operation.

    Controllers wrap each endpoint body in this; the emitted names are
    ``{event_base}.started``, ``{event_base}.completed`` and
    ``{event_base}.failed`` (uniform across the app — e.g.
    ``tickets.create.started``). The failure path classifies errors without
    exposing them: the HTTP status when the exception carries one
    (duck-typed ``status_code`` — FastAPI's HTTPException and friends) plus
    the exception class name. Never obscures tracebacks: exceptions simply
    propagate after the record. The yielded dict collects result fields
    (``op["ticket_ref"] = ...``) merged into the ``completed`` record;
    ``duration_ms`` is measured here, once, at the boundary.
    """
    started = time.perf_counter()
    flow_event(
        f"{event_base}.started",
        operation=operation,
        method=method,
        path=path,
        **fields,
    )
    extras: dict = {}

    def _emit(suffix: str, exc: Exception | None = None) -> None:
        payload = {
            "operation": operation,
            "method": method,
            "path": path,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            **fields,
            **extras,
        }
        if exc is not None:
            status = getattr(exc, "status_code", None)
            payload["status"] = status if isinstance(status, int) else None
            payload["error"] = type(exc).__name__
        flow_event(f"{event_base}.{suffix}", **payload)

    try:
        yield extras
    except Exception as exc:
        _emit("failed", exc)
        raise
    _emit("completed")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _current_span_ids():
    """(trace_id, span_id) of the active span, else (None, None)."""
    if not _OTEL_API:
        return None, None
    try:
        span = _otel_trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.is_valid:
            return ctx.trace_id, ctx.span_id
    except Exception:  # correlation must never break normal logging
        pass
    return None, None


def _fmt_trace_id(value) -> str:
    return f"{value:032x}" if value else "-"


def _fmt_span_id(value) -> str:
    return f"{value:016x}" if value else "-"


class _CorrelationFormatter(logging.Formatter):
    """Shared base: message + optional trace/span/request correlation."""

    def _correlation(self, record):
        trace_id, span_id = _current_span_ids()
        request_id = _request_id_var.get()
        return trace_id, span_id, request_id


class JsonLogFormatter(_CorrelationFormatter):
    """One JSON object per log line (machine-ingestable; always used for files)."""

    def format(self, record):
        trace_id, span_id, request_id = self._correlation(record)
        payload = {
            "log_id": uuid.uuid4().hex,
            "service_name": app_config.OTEL_SERVICE_NAME,
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_sensitive(record.getMessage()),
        }
        if request_id:
            payload["request_id"] = request_id
        if trace_id:
            payload["trace_id"] = _fmt_trace_id(trace_id)
            payload["span_id"] = _fmt_span_id(span_id)
        http = getattr(record, "http", None)
        if isinstance(http, dict):
            payload.update({k: v for k, v in http.items() if v is not None})
        if record.exc_info:
            exc_info = record.exc_info
            payload["exception_type"] = exc_info[0].__name__ if exc_info[0] else "Exception"
            # traceback text too: exception args may embed URLs/params
            payload["exc"] = _redact_sensitive(self.formatException(exc_info))
        return json.dumps(payload, ensure_ascii=False)


class ConsoleLogFormatter(_CorrelationFormatter):
    """Human format: `<HH:MM:SS> LEVEL logger message  [ids]`."""

    def format(self, record):
        trace_id, span_id, request_id = self._correlation(record)
        ts = self.formatTime(record, "%H:%M:%S")
        line = f"{ts} {record.levelname:<7} {record.name} {_redact_sensitive(record.getMessage())}"
        if trace_id:
            line += f"  trace={_fmt_trace_id(trace_id)} span={_fmt_span_id(span_id)}"
        if request_id:
            line += f"  req={request_id}"  # full id; grep/eyeball friendly
        if record.exc_info:
            line += "\n" + _redact_sensitive(self.formatException(record.exc_info))
        return line


def _make_file_handler():
    """Rotating JSON file handler, or None on failure (warn + stdout only).

    Creates the log directory first — TimedRotatingFileHandler opens the
    file lazily on first emit (delay=True), so unwritable directories would
    otherwise surface as per-record FileNotFoundError noise instead of a
    single clean warning.
    """
    try:
        log_dir = os.path.dirname(app_config.LOG_FILE_PATH)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handler = TimedRotatingFileHandler(
            filename=app_config.LOG_FILE_PATH,
            when="midnight",
            backupCount=max(1, int(app_config.LOG_FILE_RETENTION_DAYS)),
            encoding="utf-8",
            delay=True,  # open lazily; nothing written until a real record
        )
        handler.setFormatter(JsonLogFormatter())
        handler._hrdesk = True
        return handler
    except (OSError, ValueError) as exc:  # unwritable path / bad config: warn + stdout only
        get_logger().warning(f"persistent file logging disabled: {exc}")
        return None


def setup_logging() -> None:
    """Install the app root handlers (idempotent).

    Console handler format comes from LOG_FORMAT (console | json); the
    rotating file handler (LOG_TO_FILE) always writes JSON. Uvicorn's own
    loggers are untouched; silent /health + CORS preflights etc. unchanged.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_hrdesk", False):
            root.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    if app_config.LOG_FORMAT == "json":
        console_handler.setFormatter(JsonLogFormatter())
    else:
        console_handler.setFormatter(ConsoleLogFormatter())
    console_handler._hrdesk = True
    root.addHandler(console_handler)

    if app_config.LOG_TO_FILE:
        file_handler = _make_file_handler()
        if file_handler is not None:
            root.addHandler(file_handler)

    level_name = str(app_config.LOG_LEVEL or "info").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def _spans_endpoint() -> str:
    """OTLPSpanExporter uses its endpoint argument verbatim (unlike env-var
    configuration, which appends the signal path itself) — normalise both
    base-URL and full-path input styles to the canonical trace path."""
    base = app_config.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
    return base if base.endswith("/v1/traces") else base + "/v1/traces"


class _ExportErrorRateFilter(logging.Filter):
    """Collapse a flood of OTLP exporter failure lines into one per window.

    With the collector (Jaeger) down, the exporter logs a WARNING per retry
    attempt plus an ERROR per failed batch — previously dozens of lines per
    request relied on BatchSpanProcessor batching alone. This filter lets the
    FIRST failure line of each ``window_seconds`` pass, drops the rest, and
    emits one backend summary line when the next window opens with prior
    suppression. ``window <= 0`` disables the throttle entirely (config knob,
    see .env.example). Request handling is never affected by export failures.
    """

    def __init__(self, window_seconds: int):
        super().__init__()
        self._window = int(window_seconds)
        self._last_pass: float | None = None
        self._dropped = 0

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (logging API)
        if self._window <= 0:
            return True
        now = time.monotonic()
        if self._last_pass is None or now - self._last_pass >= self._window:
            if self._dropped:
                get_logger().warning(
                    "tracing export failures: %d exporter log lines suppressed "
                    "in the last %ds window — OTLP collector down? "
                    "(start Jaeger per README §11, or set TRACE_ENABLED=false)",
                    self._dropped,
                    self._window,
                )
                self._dropped = 0
            self._last_pass = now
            return True
        self._dropped += 1
        return False


def _install_exporter_log_throttle() -> None:
    """Attach the shared rate filter to the loggers that report export failures.

    One filter instance is shared so the counters span both the exporter's
    transient-retry warnings and the SDK batch-export errors. Installation
    happens once per process from setup_tracing(); a module-level guard keeps
    repeated calls from adding the same filter twice (double-counted drops).
    """
    global _EXPORT_LOG_THROTTLE
    if _EXPORT_LOG_THROTTLE is not None:
        return
    window = app_config.OTEL_EXPORT_ERROR_LOG_WINDOW_SECONDS
    if window <= 0:
        return  # throttle disabled by configuration
    _EXPORT_LOG_THROTTLE = _ExportErrorRateFilter(window)
    for logger_name in (
        "opentelemetry.exporter.otlp.proto.http.trace_exporter",
        "opentelemetry.sdk.trace",
    ):
        logging.getLogger(logger_name).addFilter(_EXPORT_LOG_THROTTLE)


_EXPORT_LOG_THROTTLE: _ExportErrorRateFilter | None = None


def setup_tracing(app) -> bool:
    """Initialize the TracerProvider + instrumentors.

    Returns
    -------
    bool
        True when instrumentation is active; False when disabled by config
        or when the OpenTelemetry packages are not installed. Export failures
        (e.g. Jaeger not running) never break request handling; their log
        noise is rate-limited by _ExportErrorRateFilter (see above).
    """
    if not app_config.TRACE_ENABLED:
        get_logger().info("tracing disabled (TRACE_ENABLED=false)")
        return False

    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        get_logger().warning(
            "tracing disabled: opentelemetry packages not installed "
            "(run pip install -r requirements.txt)"
        )
        return False

    resource = Resource.create({"service.name": app_config.OTEL_SERVICE_NAME})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=_spans_endpoint(), timeout=5))
    )
    _otel_trace.set_tracer_provider(provider)
    _install_exporter_log_throttle()

    # Server spans per /api request: extracts the frontend's traceparent and
    # joins each browser-initiated trace to its server span. /health excluded.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health")
    get_logger().info(
        f"tracing enabled -> service={app_config.OTEL_SERVICE_NAME} "
        f"otlp={app_config.OTEL_EXPORTER_OTLP_ENDPOINT}"
    )
    return True


@contextmanager
def db_span(name: str, attributes: dict | None = None):
    """Semantic span around a PostgreSQL statement.

    When tracing is off (or OTel is absent) the yielded span is None and the
    body runs unchanged — the API tracer only creates non-recording spans,
    so attribute writes stay safe. Exceptions propagate (recorded
    automatically by the SDK context manager when a real span is active).
    """
    if not _OTEL_API:
        yield None
        return
    with _otel_trace.get_tracer("hrdesk.db").start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


@contextmanager
def background_span(name: str, attributes: dict | None = None):
    """Root span for the lifespan background jobs (no request context → new trace)."""
    if not _OTEL_API:
        yield None
        return
    with _otel_trace.get_tracer("hrdesk.jobs").start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


def record_error_on_current_span(exc: Exception) -> None:
    """Mark the active request span as failed (for @app.exception_handler)."""
    if not _OTEL_API:
        return
    try:
        from opentelemetry.trace import Status, StatusCode

        span = _otel_trace.get_current_span()
        if span and span.is_recording():
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
    except Exception:  # error handling must never raise
        pass


# ---------------------------------------------------------------------------
# Request logging middleware (pure ASGI — no BaseHTTPMiddleware buffering)
# ---------------------------------------------------------------------------


class RequestLogMiddleware:
    """Request-id plumbing + one structured line per HTTP request.

    EVERY http request (including /health and CORS preflights) gets a
    ``request_id`` either client-supplied (strict format) or generated, an
    ``X-Request-ID`` response header, and the id in scope while downstream
    handlers/loggers run. The per-request log LINE is skipped for /health
    and OPTIONS to keep polling noise out of the persistent log.

    Exceptions handled inside FastAPI's ExceptionMiddleware never bubble
    here (it sits inner in the stack); the except branch covers
    transport-level failures.
    """

    SKIP_LOG_PATHS = ("/health",)

    def __init__(self, app, logger=None, header_name=REQUEST_ID_HEADER):
        self.app = app
        self.logger = logger or get_logger(REQUEST_LOGGER_NAME)
        self.header_name = header_name.encode("ascii").lower()

    @staticmethod
    def _client_request_id(scope):
        for name, value in scope.get("headers") or ():
            if name.lower() == REQUEST_ID_HEADER.encode("ascii"):
                try:
                    return value.decode("latin-1")
                except Exception:
                    return None
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(self._client_request_id(scope))
        token = _request_id_var.set(request_id)

        def send_wrapper(message):
            if message["type"] == "http.response.start":
                # Echo the request id on every response; drop any conflicting
                # inbound echo so header and logs always agree.
                headers = [
                    (name, value)
                    for (name, value) in message.get("headers", [])
                    if name.lower() != self.header_name
                ]
                headers.append((self.header_name, request_id.encode("ascii")))
                message = {**message, "headers": headers}
            return send(message)

        try:
            # Log LINE skipped for /health and preflights (noise policy),
            # but request-id + header + context still apply to everything.
            if scope["method"] == "OPTIONS" or any(
                scope.get("path", "").startswith(p) for p in self.SKIP_LOG_PATHS
            ):
                await self.app(scope, receive, send_wrapper)
                return

            start = time.perf_counter()
            status_holder = {"status": None}

            async def timed_send(message):
                if message["type"] == "http.response.start":
                    # Guard the capture — later messages (body/disconnect) have
                    # no `status` key and must not clobber it (the `-> ?` bug).
                    status_holder["status"] = message["status"]
                await send_wrapper(message)

            try:
                await self.app(scope, receive, timed_send)
            except Exception:
                self.logger.exception(
                    "request failed before response",
                    extra={"http": self._fields(scope, 500, start, request_id=request_id)},
                )
                raise
            finally:
                status = status_holder["status"]
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                self.logger.info(
                    f"{scope['method']} {scope['path']} -> "
                    f"{status if status is not None else '?'} in {duration_ms}ms",
                    extra={
                        "http": self._fields(
                            scope, status, start, duration_ms, request_id=request_id
                        )
                    },
                )
        finally:
            _request_id_var.reset(token)

    @staticmethod
    def _fields(scope, status, start, duration_ms=None, request_id=None):
        fields = {
            "source": "backend",
            "method": scope["method"],
            "path": scope["path"],  # ASGI scope path never includes the query
            "status": status,
        }
        if duration_ms is not None:
            fields["duration_ms"] = duration_ms
        fields["request_id"] = request_id
        trace_id, span_id = _current_span_ids()
        if trace_id:
            fields["trace_id"] = _fmt_trace_id(trace_id)
            if span_id:
                fields["span_id"] = _fmt_span_id(span_id)
        return fields
