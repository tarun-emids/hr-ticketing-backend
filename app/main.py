"""HR Desk API — FastAPI entrypoint.

Layering:
    app.controllers  (routers: parse request -> service call)
    app.services     (business rules; repositories injected)
    app.repositories (the only layer that touches Supabase)
    app.deps         (the DI graph wiring it together)

Run:
    uvicorn app.main:app --reload --port 8000
Docs at http://localhost:8000/docs
"""
import asyncio
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config as app_config
from app.controllers import attachments, auth, drafts, notifications, tickets, users
from app.services.notification_service import (
    SLA_SWEEP_INTERVAL_SECONDS,
    NotificationService,
)
from app.repositories.notification_repository import NotificationRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository


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
        try:
            await jobs
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="HR Desk API",
    description="Ticketing backend for the Emids HR Desk frontend (Supabase Postgres + Storage).",
    version="0.1.3",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.CORS_ORIGINS or ["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api mount: frontend will call e.g. http://localhost:8000/api/tickets
app.include_router(auth.router, prefix="/api")
app.include_router(tickets.router, prefix="/api")
app.include_router(attachments.router, prefix="/api")
app.include_router(drafts.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(users.router, prefix="/api")


@app.get("/health")
def health():
    """Liveness only — does not touch Supabase."""
    return {"ok": True}


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    """Dev handler: any uncaught server error returns readable JSON instead of
    a bare 500, and still prints the full traceback to the console."""
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )
