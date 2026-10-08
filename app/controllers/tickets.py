"""Ticket endpoints: CRUD, thread, lifecycle and assignment.

No rules here — every handler delegates to TicketService and returns its
result. Route paths and declaration order match the previous routers
exactly (frontend contract / FastAPI path-matching unchanged).
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
from app.services.ticket_service import TicketService

router = APIRouter(tags=["tickets"])


@router.post("/tickets", status_code=201)
def create_ticket(payload: TicketCreate, svc: TicketService = Depends(get_ticket_service)):
    """POST /tickets — create a ticket (guards: employee exists + role check).

    Body accepts camelCase (employeeId, ...) thanks to the alias config.
    """
    return svc.create(
        employee_id=payload.employee_id,
        category=payload.category,
        subject=payload.subject,
        description=payload.description,
        priority=payload.priority,
    )


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
    return svc.list(
        status=status,
        category=category,
        priority=priority,
        employee_id=employeeId,
        assignee_id=assigneeId,
        q=q,
        unassigned=unassigned,
        limit=limit,
    )


@router.get("/tickets/{tid}")
def get_ticket(tid: str, svc: TicketService = Depends(get_ticket_service)):
    """GET /tickets/{TKT-123 | uuid} — full ticket incl. thread."""
    return svc.get(tid)


@router.post("/tickets/{tid}/replies")
def add_reply(tid: str, payload: ReplyCreate, svc: TicketService = Depends(get_ticket_service)):
    """POST /tickets/{id}/replies — store.js addReply parity."""
    return svc.add_reply(tid, author_id=payload.author_id, text=payload.text)


@router.patch("/tickets/{tid}/status")
def update_status(tid: str, payload: StatusUpdate, svc: TicketService = Depends(get_ticket_service)):
    """store.js updateStatus parity: Resolved stamps resolvedAt, Closed also
    stamps closedBy, reopening clears both."""
    return svc.update_status(tid, status=payload.status, actor_id=payload.actor_id)


@router.patch("/tickets/{tid}/assignee")
def assign_ticket(tid: str, payload: AssigneeUpdate, svc: TicketService = Depends(get_ticket_service)):
    return svc.assign_by_key(tid, payload.assignee_id)


@router.patch("/tickets/{tid}/priority")
def set_priority(tid: str, payload: PriorityUpdate, svc: TicketService = Depends(get_ticket_service)):
    return svc.set_priority(tid, payload.priority)


@router.patch("/tickets/{tid}/category")
def set_category(tid: str, payload: CategoryUpdate, svc: TicketService = Depends(get_ticket_service)):
    return svc.set_category(tid, payload.category)


@router.post("/tickets/{tid}/auto-assign")
def auto_assign(tid: str, svc: TicketService = Depends(get_ticket_service)):
    """Route a ticket to the least-loaded HR agent (open count, then total)."""
    return svc.auto_assign(tid)


@router.get("/agents/workload")
def workload(svc: TicketService = Depends(get_ticket_service)):
    """GET /agents/workload — per-agent open/total ticket counts."""
    return svc.agent_workload()
