"""Frontend log ingestion — browser events into the app's existing logs.

Writes accepted events through the app's standard logging configuration
(``logging.getLogger("hrdesk.frontend")`` → root handlers → the SAME rotating
``backend/logs/app.log`` every backend record lands in). Nothing here touches
Supabase, creates files, or changes handlers.

Safety rails (see §5 of the observability spec):
- size caps come from the DTO (≤20 events/batch, ≤200 chars endpoint, …);
- untrusted strings are truncated and pass through the same
  ``_redact_sensitive`` masking the backend emitters use;
- correlation ids are validated with the SAME regex as client request ids;
- a small in-memory per-IP rate limiter guards the endpoint. It holds one
  deque of timestamps per client IP (few entries each) and never queues work.
"""
import logging
import time
from collections import deque, defaultdict

from app.models import LogIngestRequest
from app.observability import _redact_sensitive, resolve_request_id

LOGGER_NAME = "hrdesk.frontend"
LEVELS = {"INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}
RATE_LIMIT_REQUESTS_PER_MINUTE = 60

# module-level so the limiter survives per-request service construction
_RATE_HITS: dict[str, deque] = defaultdict(deque)


def _allow(client_ip: str) -> bool:
    """Sliding-window 60 POSTs/minute per client IP (cheap, no dependencies)."""
    now = time.monotonic()
    hits = _RATE_HITS[client_ip]
    while hits and now - hits[0] > 60.0:
        hits.popleft()
    if len(hits) >= RATE_LIMIT_REQUESTS_PER_MINUTE:
        return False
    hits.append(now)
    return True


class LogIngestService:
    """Validated frontend events → the existing logging pipeline."""

    def allow(self, client_ip: str) -> bool:
        return _allow(client_ip)

    def ingest(self, payload: LogIngestRequest) -> int:
        """Log every accepted event; returns the count written."""
        logger = logging.getLogger(LOGGER_NAME)
        written = 0
        for event in payload.events:
            level = LEVELS[event.level]
            message = _redact_sensitive(
                f"[frontend] {event.event}"
                + (f" {event.method} {event.endpoint}" if event.endpoint else "")
            )
            logger.log(
                level,
                message[:500],
                extra={
                    "http": {
                        "source": "frontend",
                        "frontend_log_id": event.log_id,
                        "correlation_id": resolve_request_id(event.correlation_id),
                        "event": event.event,
                        "method": event.method,
                        "path": event.endpoint,
                        "status": event.status_code,
                        "duration_ms": event.duration_ms,
                        "occurred_at": event.occurred_at,
                    }
                },
            )
            written += 1
        return written
