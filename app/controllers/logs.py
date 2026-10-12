"""Frontend log ingestion endpoint (POST /api/logs/ingest).

Accepts a small validated batch of browser-side log events and writes them
through the app's EXISTING logging configuration — the same rotating
``backend/logs/app.log`` backend records land in — each tagged with its
correlation id, so a frontend submission and the backend request that handled
it can be found together.

Design guardrails (see §4/§5 of the observability spec):
- Pydantic validates every field (lengths, id formats, level allowlist);
- a cheap per-IP sliding-window rate limit makes log-dos expensive;
- the endpoint never throws non-HTTP exceptions: ingestion failures are
  logged on our side and still return 202 (logging must never break
  ticket flows, including this one).

Observability: deliberately NO started/completed events here — the ingest
hop already gets its per-request middleware line, and layer events would
make the log sink self-referential. Only rejections get a dedicated record:
``logs.ingest.rejected`` (WARNING, rate limiter tripped) — diagnosable
without logging any payload contents; validation rejections stay visible
through the standard 422 middleware line.
"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps import get_log_ingest_service
from app.models import LogIngestRequest
from app.observability import flow_warning
from app.services.log_ingest_service import LogIngestService

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("/ingest", status_code=202)
def ingest_frontend_events(payload: LogIngestRequest,
                           request: Request,
                           svc: LogIngestService = Depends(get_log_ingest_service)):
    """Accept 1..20 validated frontend log events; writes to the shared log."""
    client_ip = request.client.host if request.client else "unknown"
    if not svc.allow(client_ip):
        # Safe diagnostic only: the threshold — no payload contents; the
        # hop's own request_id arrives via the record formatters.
        flow_warning("logs.ingest.rejected",
                     operation="logs.ingest",
                     limit_per_minute=60)
        raise HTTPException(status_code=429, detail="Too many log events; slow down.")
    try:
        return {"accepted": svc.ingest(payload)}
    except Exception:  # persisting must never break the client's workflow
        from app.observability import get_logger

        get_logger().exception("frontend log ingestion failed (payload dropped)")
        return {"accepted": 0}
