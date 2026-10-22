"""HR Desk API — FastAPI entrypoint.

Layering:
    app.controllers  (routers: parse request -> service call)
    app.services     (business rules; repositories injected)
    app.repositories (the only layer that touches Supabase)
    app.deps         (the DI graph wiring it together)

Observability (all opt-out via env — see app/observability.py and README §11):
    - setup_logging(): console (console|json) + rotating JSON file handlers
    - RequestLogMiddleware: request_id (validated client id or fresh UUID),
      X-Request-ID response header on every request, one log line per
      request (method, path, status, ms; /health + preflights unlogged)
    - setup_tracing(app): OpenTelemetry server+httpx spans, OTLP export,
      joining the frontend's W3C traceparent

Run:
    uvicorn app.main:app --reload --port 8000
Docs at http://localhost:8000/docs
"""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config as app_config
from app.controllers import (
    attachments,
    auth,
    drafts,
    knowledge_base,
    logs,
    notifications,
    tickets,
    users,
)
from app.resilience import breakers_snapshot
from app.services.notification_service import (
    SLA_SWEEP_INTERVAL_SECONDS,
    NotificationService,
)
from app.repositories.notification_repository import NotificationRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.observability import (
    RequestLogMiddleware,
    get_logger,
    record_error_on_current_span,
    setup_logging,
    setup_tracing,
)
from app.repositories.notification_repository import NotificationRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.resilience import breakers_snapshot
from app.services.notification_service import (
    SLA_SWEEP_INTERVAL_SECONDS,
    NotificationService,
)

setup_logging()
log = get_logger()


def _notification_service_for_jobs() -> NotificationService:
    """Background-scheduler instance, built directly (not via request-scoped
    Depends) from the same config singleton the DI graph uses."""
    client = app_config.get_client()
    return NotificationService(
        NotificationRepository(client),
        UserRepository(client),
        TicketRepository(client),
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Background jobs: first-response SLA sweep + notification retention.
    Runs immediately on boot, then every SLA_SWEEP_INTERVAL_SECONDS. Each job
    swallows its own errors, so a Supabase outage only pauses them."""
    svc = _notification_service_for_jobs()

    async def _jobs():
        while True:
            await asyncio.to_thread(svc.run_sla_sweep)
            await asyncio.to_thread(svc.run_retention_cleanup)
            await asyncio.sleep(SLA_SWEEP_INTERVAL_SECONDS)

    jobs = asyncio.create_task(_jobs())
    try:
        yield
    finally:
        jobs.cancel()
        with suppress(asyncio.CancelledError):
            await jobs


app = FastAPI(
    title="HR Desk API",
    description="Ticketing backend for the Emids HR Desk frontend (Supabase Postgres + Storage).",
    version="0.1.3",
    lifespan=lifespan,
    # FastAPI's native telemetry would auto-add OTLP exporters from
    # OTEL_EXPORTER_OTLP_ENDPOINT for traces/metrics/logs on top of our own
    # setup — the metric one was the source of the per-minute
    # "Failed to export metrics batch code: 404" (Jaeger does not ingest
    # metrics). Tracing/logging here is configured explicitly in
    # app/observability.py; FastAPI's env auto-config is ours to own.
    telemetry={"auto_configure": False},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.CORS_ORIGINS or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # so the browser can read the request-id echo in cross-origin dev
    expose_headers=["X-Request-ID"],
)

# One structured line per API request (skips /health + CORS preflights).
app.add_middleware(RequestLogMiddleware)

# /api mount: frontend will call e.g. http://localhost:8000/api/tickets
app.include_router(auth.router, prefix="/api")
app.include_router(tickets.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(drafts.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(users.router, prefix="/api")
# frontend log events → the same backend/logs/app.log backend records use
app.include_router(logs.router, prefix="/api")
# knowledge base (policy library: search, metadata, signed PDF URLs)
app.include_router(knowledge_base.router, prefix="/api")


@app.get("/")
def root():
    """Service banner: bare root used to answer a bare 404, which read like an
    error. The API surface lives under /api — point humans at the useful doors."""
    return {
        "name": "HR Desk API",
        "status": "running",
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    """Liveness only — does not touch Supabase."""
    return {"ok": True}


@app.get("/health/deps")
def health_deps():
    """Read-only readiness view: circuit-breaker state per Supabase surface.

    Makes breaker transitions observable with curl during an outage demo or
    incident (state flips closed -> open; failures counts; secondsUntilProbe
    while open). Touches no Supabase call, so it answers even mid-outage.
    """
    return {"breakers": breakers_snapshot()}


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """Dev handler: any uncaught server error returns readable JSON instead of
    a bare 500. The full traceback goes to the structured log (and to the
    active tracing span); the response contract is unchanged."""
    log.exception(
        f"unhandled server error: {request.method} {request.url.path}",
        extra={"http": {"method": request.method, "path": request.url.path}},
    )
    record_error_on_current_span(exc)
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


# Tracing LAST, after every middleware/route is registered. No-op when
# TRACE_ENABLED=false or the OTel packages are not installed.
setup_tracing(app)
