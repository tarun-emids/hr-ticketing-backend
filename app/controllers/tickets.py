"""Ticket endpoints: CRUD, thread, lifecycle and assignment.

No rules here — every handler delegates to TicketService and returns its
result. Route paths and declaration order match the previous routers
exactly (frontend contract / FastAPI path-matching unchanged).

Observability: every endpoint body is wrapped in ``flow_operation`` — the
standard started/completed/failed trio under the ``hrdesk.flow`` logger
(``tickets.create.started`` … ``tickets.list.completed``), with safe result
fields (ticket ref, row counts) and durations. Deeper layers add their own
milestones: services emit ``ticket.service.*``, repositories
``ticket.repository.*`` (create/insert + update paths). Ticket content
(subject/description/replies) is never logged; refs, statuses, categories,
priorities and UUIDs only.
"""

from typing import Optional

from fastapi import APIRouter, Depends

from app.deps import get_ticket_service
from app.models import (
    AssigneeUpdate,
    CategoryUpdate,
    PriorityUpdate,
    ReplyCreate,
    StatusUpdate,
    TicketCreate,
)
from app.observability import flow_operation
from app.services.ticket_service import TicketService

router = APIRouter(tags=["tickets"])


@router.post("/tickets", status_code=201)
def create_ticket(payload: TicketCreate, svc: TicketService = Depends(get_ticket_service)):
    """POST /tickets — create a ticket (guards: employee exists + role check).

    Body accepts camelCase (employeeId, ...) thanks to the alias config.
    """
    with flow_operation(
        "tickets.create",
        operation="tickets.create",
        method="POST",
        path="/api/tickets",
    ) as op:
        result = svc.create(
            employee_id=payload.employee_id,
            category=payload.category,
            subject=payload.subject,
            description=payload.description,
            priority=payload.priority,
        )
        op["ticket_ref"] = _ref_of(result)
        op["status"] = "created"
        return result


def _ref_of(result):
    """The serialized ticket presents the TKT-ref as ``id``; raw rows carry
    ``ref`` too — either way only the safe human ref reaches the log."""
    return (result or {}).get("ref") or (result or {}).get("id")


@router.get("/tickets")
def list_tickets(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    employeeId: Optional[str] = None,
    assigneeId: Optional[str] = None,
    q: Optional[str] = None,
    unassigned: bool = False,
    limit: int = 200,
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /tickets — newest-first by updatedAt (list items carry empty turns;
    load a single ticket for the full thread)."""
    # ``q`` is free text — only its PRESENCE is logged, never the value.
    with flow_operation(
        "tickets.list",
        operation="tickets.list",
        method="GET",
        path="/api/tickets",
        status=status,
        category=category,
        priority=priority,
        employee_id=employeeId,
        assignee_id=assigneeId,
        search=bool(q),
        unassigned=unassigned,
        limit=limit,
    ) as op:
        result = svc.list(
            status=status,
            category=category,
            priority=priority,
            employee_id=employeeId,
            assignee_id=assigneeId,
            q=q,
            unassigned=unassigned,
            limit=limit,
        )
        op["count"] = len(result)
        return result


@router.get("/tickets/{tid}")
def get_ticket(tid: str, svc: TicketService = Depends(get_ticket_service)):
    """GET /tickets/{TKT-123 | uuid} — full ticket incl. thread."""
    with flow_operation(
        "tickets.get",
        operation="tickets.get",
        method="GET",
        path=f"/api/tickets/{tid}",
    ) as op:
        result = svc.get(tid)
        op["ticket_ref"] = result.get("id")
        op["turns"] = len(result.get("turns") or [])
        return result


@router.post("/tickets/{tid}/replies")
def add_reply(tid: str, payload: ReplyCreate, svc: TicketService = Depends(get_ticket_service)):
    """POST /tickets/{id}/replies — store.js addReply parity."""
    with flow_operation(
        "tickets.reply",
        operation="tickets.reply",
        method="POST",
        path=f"/api/tickets/{tid}/replies",
    ) as op:
        result = svc.add_reply(tid, author_id=payload.author_id, text=payload.text)
        op["ticket_ref"] = result.get("id")
        op["turns"] = len(result.get("turns") or [])
        return result


@router.patch("/tickets/{tid}/status")
def update_status(
    tid: str, payload: StatusUpdate, svc: TicketService = Depends(get_ticket_service)
):
    """store.js updateStatus parity: Resolved stamps resolvedAt, Closed also
    stamps closedBy, reopening clears both."""
    with flow_operation(
        "tickets.status",
        operation="tickets.status",
        method="PATCH",
        path=f"/api/tickets/{tid}/status",
    ) as op:
        result = svc.update_status(tid, status=payload.status, actor_id=payload.actor_id)
        op["ticket_ref"] = result.get("id")
        op["new_status"] = result.get("status")
        return result


@router.patch("/tickets/{tid}/assignee")
def assign_ticket(tid: str, payload: AssigneeUpdate, svc: TicketService = Depends(get_ticket_service)):
    with flow_operation(
        "tickets.assign",
        operation="tickets.assign",
        method="PATCH",
        path=f"/api/tickets/{tid}/assignee",
    ) as op:
        result = svc.assign_by_key(tid, payload.assignee_id)
        op["ticket_ref"] = result.get("id")
        op["assignee_id"] = result.get("assigneeId")
        return result


@router.patch("/tickets/{tid}/priority")
def set_priority(tid: str, payload: PriorityUpdate, svc: TicketService = Depends(get_ticket_service)):
    with flow_operation(
        "tickets.priority",
        operation="tickets.priority",
        method="PATCH",
        path=f"/api/tickets/{tid}/priority",
    ) as op:
        result = svc.set_priority(tid, payload.priority)
        op["ticket_ref"] = result.get("id")
        return result


@router.patch("/tickets/{tid}/category")
def set_category(tid: str, payload: CategoryUpdate, svc: TicketService = Depends(get_ticket_service)):
    with flow_operation(
        "tickets.category",
        operation="tickets.category",
        method="PATCH",
        path=f"/api/tickets/{tid}/category",
    ) as op:
        result = svc.set_category(tid, payload.category)
        op["ticket_ref"] = result.get("id")
        return result


@router.post("/tickets/{tid}/auto-assign")
def auto_assign(tid: str, svc: TicketService = Depends(get_ticket_service)):
    """Route a ticket to the least-loaded HR agent (open count, then total)."""
    with flow_operation(
        "tickets.auto_assign",
        operation="tickets.auto_assign",
        method="POST",
        path=f"/api/tickets/{tid}/auto-assign",
    ) as op:
        result = svc.auto_assign(tid)
        op["ticket_ref"] = result.get("id")
        op["routed_to"] = (result.get("routedTo") or {}).get("id")
        return result


@router.get("/agents/workload")
def workload(svc: TicketService = Depends(get_ticket_service)):
    """GET /agents/workload — per-agent open/total ticket counts."""
    with flow_operation(
        "agents.workload",
        operation="agents.workload",
        method="GET",
        path="/api/agents/workload",
    ) as op:
        result = svc.agent_workload()
        op["agents"] = len(result)
        return result
