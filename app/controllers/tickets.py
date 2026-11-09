"""Ticket endpoints: CRUD, thread, lifecycle and assignment.

No rules here — every handler delegates to TicketService and returns its
result. Route paths and declaration order match the previous routers
exactly (frontend contract / FastAPI path-matching unchanged).

IDENTITY: every acting user comes from the BEARER token
(``get_current_account``), never from a client claim. The legacy
``viewerId``/``employeeId``/``actorId``/``authorId`` params stay accepted for
callers that still send them, but a claim that disagrees with the token is a
forgery attempt and answers 403 instead of being honoured. Service-side
gate helpers (require_staff, viewer-scoped reads) receive the
bearer-resolved account as their ``viewer``.

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

from fastapi import APIRouter, Depends, HTTPException

from app.deps import (
    acting_user_id,
    get_current_account,
    get_current_agent,
    get_ticket_service,
)
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

TICKET_PAGE_SIZE_DEFAULT = 25
TICKET_PAGE_SIZE_MAX = 100


def _viewer(account: dict, claimed: Optional[str], svc: TicketService) -> dict:
    """The viewer for service-level gating is the bearer account itself.
    A claimed viewerId from the client is only consistent glue: allowed
    when it agrees with the token, rejected as forgery otherwise. (The
    service-side require_viewer resolution stays reachable only through
    direct service use — over HTTP the token is the source of truth.)"""
    acting_user_id(account, claimed)
    return account


def _ref_of(result):
    """The serialized ticket presents the TKT-ref as ``id``; raw rows carry
    ``ref`` too — either way only the safe human ref reaches the log."""
    return (result or {}).get("ref") or (result or {}).get("id")


@router.post("/tickets", status_code=201)
def create_ticket(
    payload: TicketCreate,
    account: dict = Depends(get_current_account),
    svc: TicketService = Depends(get_ticket_service),
):
    """POST /tickets — create a ticket (guards: employee exists + role check).

    Body accepts camelCase (employeeId, ...) thanks to the alias config.
    The filing identity comes from the bearer token — a client-supplied
    employeeId that disagrees with it is rejected instead of honoured.
    """
    with flow_operation(
        "tickets.create",
        operation="tickets.create",
        method="POST",
        path="/api/tickets",
    ) as op:
        # The identity decision sits INSIDE the instrumented span on purpose:
        # a rejected impersonation attempt still emits started → failed(403)
        # with the request id, so every rejection leaves an audit trail.
        employee_id = acting_user_id(account, payload.employee_id)
        result = svc.create(
            employee_id=employee_id,
            category=payload.category,
            subject=payload.subject,
            description=payload.description,
            priority=payload.priority,
        )
        op["ticket_ref"] = _ref_of(result)
        op["status"] = "created"
        return result


@router.get("/tickets")
def list_tickets(
    viewerId: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    employeeId: Optional[str] = None,
    assigneeId: Optional[str] = None,
    q: Optional[str] = None,
    unassigned: bool = False,
    page: int = 1,
    pageSize: int = TICKET_PAGE_SIZE_DEFAULT,
    sort: str = "updated",
    order: str = "desc",
    account: dict = Depends(get_current_account),
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /tickets — the paginated envelope is the single contract:
    {items, page, pageSize, total, hasNext}. page >= 1; pageSize 1..100
    (default 25); sort in updated|created|priority|subject; order asc|desc.
    Row visibility is scoped to the bearer identity: employees always see
    only their own tickets (an employeeId filter that disagrees is a 403);
    staff may filter by anyone or none."""
    viewer = _viewer(account, viewerId, svc)
    if account.get("role") == "employee" and employeeId and employeeId != str(account["id"]):
        raise HTTPException(status_code=403, detail="Employees may only list their own tickets.")
    if page < 1:
        raise HTTPException(status_code=422, detail="page must be >= 1")
    if pageSize < 1 or pageSize > TICKET_PAGE_SIZE_MAX:
        raise HTTPException(
            status_code=422,
            detail=f"pageSize must be between 1 and {TICKET_PAGE_SIZE_MAX}",
        )
    # ``q`` is free text — only its PRESENCE is logged, never the value.
    with flow_operation(
        "tickets.list",
        operation="tickets.list",
        method="GET",
        path="/api/tickets",
        viewer_id=viewer["id"],
        status=status,
        category=category,
        priority=priority,
        employee_id=employeeId,
        assignee_id=assigneeId,
        search=bool(q),
        unassigned=unassigned,
        page=page,
        pageSize=pageSize,
        sort=sort,
        order=order,
    ) as op:
        result = svc.list_paged(
            viewer=viewer,
            page=page,
            page_size=pageSize,
            sort=sort,
            order=order,
            status=status,
            category=category,
            priority=priority,
            employee_id=employeeId,
            assignee_id=assigneeId,
            q=q,
            unassigned=unassigned,
        )

        op["count"] = len(result["items"])
        return result


@router.get("/tickets/{tid}")
def get_ticket(
    tid: str,
    viewerId: Optional[str] = None,
    account: dict = Depends(get_current_account),
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /tickets/{TKT-123 | uuid} — full ticket incl. thread, gated by the
    bearer identity (employees open their own tickets only; staff open any).
    An out-of-scope ticket answers KB-style 403, an unknown one 404."""
    viewer = _viewer(account, viewerId, svc)
    with flow_operation(
        "tickets.get",
        operation="tickets.get",
        method="GET",
        path=f"/api/tickets/{tid}",
        viewer_id=viewer["id"],
    ) as op:
        result = svc.get(tid, viewer=viewer)
        op["ticket_ref"] = result.get("id")
        op["turns"] = len(result.get("turns") or [])
        return result


@router.post("/tickets/{tid}/replies")
def add_reply(
    tid: str,
    payload: ReplyCreate,
    account: dict = Depends(get_current_account),
    svc: TicketService = Depends(get_ticket_service),
):
    """POST /tickets/{id}/replies — store.js addReply parity. The author is
    the bearer-token identity; a mismatching client authorId is rejected."""
    author_id = acting_user_id(account, payload.author_id)
    with flow_operation(
        "tickets.reply",
        operation="tickets.reply",
        method="POST",
        path=f"/api/tickets/{tid}/replies",
    ) as op:
        result = svc.add_reply(tid, author_id=author_id, text=payload.text)
        op["ticket_ref"] = result.get("id")
        op["turns"] = len(result.get("turns") or [])
        return result


@router.patch("/tickets/{tid}/status")
def update_status(
    tid: str,
    payload: StatusUpdate,
    account: dict = Depends(get_current_agent),
    svc: TicketService = Depends(get_ticket_service),
):
    """Store.js updateStatus parity: Resolved stamps resolvedAt, Closed also
    stamps closedBy, reopening clears both. Agent/admin routes only — the
    acting user comes from the token, never from the body."""
    with flow_operation(
        "tickets.status",
        operation="tickets.status",
        method="PATCH",
        path=f"/api/tickets/{tid}/status",
        actor_id=str(account["id"]),
    ) as op:
        result = svc.update_status(
            tid, status=payload.status, actor_id=acting_user_id(account, payload.actor_id)
        )
        op["ticket_ref"] = result.get("id")
        op["new_status"] = result.get("status")
        return result


@router.patch("/tickets/{tid}/assignee")
def assign_ticket(
    tid: str,
    payload: AssigneeUpdate,
    viewerId: Optional[str] = None,
    account: dict = Depends(get_current_agent),
    svc: TicketService = Depends(get_ticket_service),
):
    """PATCH /tickets/{id}/assignee — staff-only (HR agent or admin) via the
    bearer gate; the acting identity never comes from a client claim."""
    viewer = _viewer(account, viewerId, svc)
    with flow_operation(
        "tickets.assign",
        operation="tickets.assign",
        method="PATCH",
        path=f"/api/tickets/{tid}/assignee",
        actor_id=str(account["id"]),
    ) as op:
        result = svc.assign_by_key(tid, payload.assignee_id)
        op["ticket_ref"] = result.get("id")
        op["assignee_id"] = result.get("assigneeId")
        return result


@router.patch("/tickets/{tid}/priority")
def set_priority(
    tid: str,
    payload: PriorityUpdate,
    account: dict = Depends(get_current_agent),
    svc: TicketService = Depends(get_ticket_service),
):
    with flow_operation(
        "tickets.priority",
        operation="tickets.priority",
        method="PATCH",
        path=f"/api/tickets/{tid}/priority",
        actor_id=str(account["id"]),
    ) as op:
        result = svc.set_priority(tid, payload.priority)
        op["ticket_ref"] = result.get("id")
        return result


@router.patch("/tickets/{tid}/category")
def set_category(
    tid: str,
    payload: CategoryUpdate,
    account: dict = Depends(get_current_agent),
    svc: TicketService = Depends(get_ticket_service),
):
    with flow_operation(
        "tickets.category",
        operation="tickets.category",
        method="PATCH",
        path=f"/api/tickets/{tid}/category",
        actor_id=str(account["id"]),
    ) as op:
        result = svc.set_category(tid, payload.category)
        op["ticket_ref"] = result.get("id")
        return result


@router.post("/tickets/{tid}/auto-assign")
def auto_assign(
    tid: str,
    account: dict = Depends(get_current_agent),
    svc: TicketService = Depends(get_ticket_service),
):
    """Route a ticket to the least-loaded HR agent (open count, then total)."""
    with flow_operation(
        "tickets.auto_assign",
        operation="tickets.auto_assign",
        method="POST",
        path=f"/api/tickets/{tid}/auto-assign",
        actor_id=str(account["id"]),
    ) as op:
        result = svc.auto_assign(tid)
        op["ticket_ref"] = result.get("id")
        op["routed_to"] = (result.get("routedTo") or {}).get("id")
        return result


@router.get("/agents/workload")
def workload(
    account: dict = Depends(get_current_agent),
    svc: TicketService = Depends(get_ticket_service),
):
    """GET /agents/workload — per-agent open/total ticket counts (staff only)."""
    with flow_operation(
        "agents.workload",
        operation="agents.workload",
        method="GET",
        path="/api/agents/workload",
    ) as op:
        result = svc.agent_workload()
        op["agents"] = len(result)
        return result
