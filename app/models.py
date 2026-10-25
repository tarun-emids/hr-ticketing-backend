"""Request models (DTOs) + response serializers.

Request DTOs and the row serializers live here — the contract between HTTP
and the service layer. Serializers convert snake_case PostgreSQL rows into the
exact camelCase shape the frontend's `src/data/store.js` works with, so the
API layer can be dropped in without touching UI code.

(The agent pickup reply text moved to services/ticket_service.py — it is a
domain message, not a schema concern.)
"""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

CATEGORIES = ["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"]
PRIORITIES = ["Low", "Medium", "High", "Urgent"]
STATUSES = ["Open", "In Progress", "Waiting on Employee", "Resolved", "Closed"]


class CamelModel(BaseModel):
    """Accepts camelCase keys from the frontend, exposes python fields."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class TicketCreate(CamelModel):
    employee_id: str
    category: Literal["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"]
    subject: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=10_000)
    priority: Literal["Low", "Medium", "High", "Urgent"] = "Medium"


class DraftCreate(CamelModel):
    employee_id: str
    category: Literal["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"] = "Other"
    subject: str = Field(default="", max_length=200)
    description: str = Field(default="", max_length=10_000)
    priority: Literal["Low", "Medium", "High", "Urgent"] = "Medium"


class DraftUpdate(CamelModel):
    category: Optional[Literal["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"]] = (
        None
    )
    subject: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10_000)
    priority: Optional[Literal["Low", "Medium", "High", "Urgent"]] = None


class DraftSubmit(CamelModel):
    employee_id: str


class ReplyCreate(CamelModel):
    author_id: str
    text: str = Field(min_length=1, max_length=5_000)


class NotificationRead(CamelModel):
    """Acting user for notification reads (mock-auth stand-in for a token)."""

    user_id: str


class StatusUpdate(CamelModel):
    status: Literal["Open", "In Progress", "Waiting on Employee", "Resolved", "Closed"]
    actor_id: str


class AssigneeUpdate(CamelModel):
    assignee_id: Optional[str] = None


class PriorityUpdate(CamelModel):
    priority: Literal["Low", "Medium", "High", "Urgent"]


class CategoryUpdate(CamelModel):
    category: Literal["Payroll", "Leave", "Benefits", "Onboarding", "Policy", "Other"]


# ---------------------------------------------------------------------------
# Frontend log ingestion (POST /api/logs/ingest) — validated DTOs so untrusted
# browser payloads never reach the logging system. Batches are small and
# every free-form field is length-capped; the server re-stamps its own ids
# and timestamps (see services/log_ingest_service.py).
#
# trace_id/span_id: the ORIGINAL browser operation's trace context (from the
# frontend's own OTel SDK span), strict lowercase hex per the W3C traceparent
# format. Optional — events without tracing enabled omit them, and the
# ingest service stamps them only as a complete pair.
# ---------------------------------------------------------------------------

_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{7,63}$"
_W3C_TRACE_ID_PATTERN = r"^[0-9a-f]{32}$"
_W3C_SPAN_ID_PATTERN = r"^[0-9a-f]{16}$"


class FrontendLogEvent(CamelModel):
    log_id: str = Field(pattern=_ID_PATTERN, max_length=64)
    correlation_id: Optional[str] = Field(default=None, pattern=_ID_PATTERN, max_length=64)
    level: Literal["INFO", "WARNING", "ERROR"] = "INFO"
    event: str = Field(min_length=3, max_length=64)
    method: Optional[Literal["GET", "POST", "PATCH", "PUT", "DELETE"]] = None
    endpoint: Optional[str] = Field(default=None, max_length=200)
    status_code: Optional[int] = Field(default=None, ge=100, le=599)
    duration_ms: Optional[float] = Field(default=None, ge=0, le=120_000)
    trace_id: Optional[str] = Field(default=None, pattern=_W3C_TRACE_ID_PATTERN, max_length=64)
    span_id: Optional[str] = Field(default=None, pattern=_W3C_SPAN_ID_PATTERN, max_length=64)
    occurred_at: str = Field(min_length=10, max_length=40)


class LogIngestRequest(CamelModel):
    """Small batch of frontend events (endpoint is rate-limited per client)."""

    events: list[FrontendLogEvent] = Field(min_length=1, max_length=20)


# Assistant (app/rag) ---------------------------------------------------------

class AssistantQuestion(CamelModel):
    """One grounded question to the HR assistant ([REF ¶block] citations
    resolved server-side; the answer never depends on chat history)."""

    employee_id: str
    question: str = Field(min_length=2, max_length=500)


# ---------------------------------------------------------------------------
# Serializers (PostgreSQL row -> API/frontend shape)
# ---------------------------------------------------------------------------


def turn_out(r: dict) -> dict:
    return {
        "authorId": r["author_id"],
        "role": r["author_role"],
        "text": r["body"],
        "at": r["created_at"],
    }


def user_out(u: dict) -> dict:
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"]}


def attachment_out(row: dict) -> Optional[dict]:
    if not row.get("attachment_path"):
        return None
    return {
        "name": row.get("attachment_name"),
        "size": row.get("attachment_size"),
        "path": row["attachment_path"],
        "url": None,  # filled in by /tickets/{id}/attachment (signed URL)
    }


def ticket_out(row: dict, replies: list[dict]) -> dict:
    """Shape matches the mock ticket objects in src/data/tickets.js."""
    return {
        "id": row["ref"],  # e.g. "TKT-101" — what the frontend uses in URLs
        "uuid": row["id"],  # raw Postgres uuid, mostly for admin/debugging
        "employeeId": row["employee_id"],
        "category": row["category"],
        "subject": row["subject"],
        "description": row["description"],
        "priority": row["priority"],
        "status": row["status"],
        "assigneeId": row.get("assignee_id"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "firstReplyAt": row.get("first_reply_at"),
        "resolvedAt": row.get("resolved_at"),
        "closedBy": row.get("closed_by"),
        "turns": [turn_out(r) for r in (replies or [])],
        "attachment": attachment_out(row),
    }


def draft_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "employeeId": row["employee_id"],
        "category": row["category"],
        "subject": row["subject"],
        "description": row["description"],
        "priority": row["priority"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "attachment": attachment_out(row),
    }


def kb_doc_out(row: dict) -> dict:
    """Knowledge-base document metadata — searchable-card shape for the
    frontend. The PDF URL is never embedded: short-lived signed links are
    minted only through GET /kb/{slug}/file, behind the same visibility gate."""
    return {
        "slug": row["slug"],
        "ref": row.get("ref"),
        "title": row["title"],
        "category": row.get("category", "General"),
        "audience": row["audience"],  # 'employee' | 'hr' (agents/admin see both pools)
        "summary": row.get("summary", ""),
        "keywords": [k.strip() for k in (row.get("keywords") or "").split(",") if k.strip()],
        "version": row.get("version", "v1.0"),
        "effectiveDate": row.get("effective_date"),
        "pages": row.get("page_count"),
        "fileSize": row.get("file_size"),
        "updatedAt": row.get("updated_at"),
    }
