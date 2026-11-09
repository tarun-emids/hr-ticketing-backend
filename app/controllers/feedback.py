"""Feedback endpoints (ticket-closure rating by the ticket's employee).

IDENTITY: the acting user comes from the bearer token, never from a client
claim — only the ticket owner can submit their rating, and only the owner or
HR staff can read it. A claimed user_id that disagrees with the token is
rejected instead of honoured.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Response

from app.deps import acting_user_id, get_current_account, get_feedback_service
from app.models import FeedbackCreate
from app.observability import flow_operation
from app.services.feedback_service import FeedbackService

router = APIRouter(tags=["feedback"])


@router.post("/tickets/{tid}/feedback")
def submit_feedback(
    tid: str,
    payload: FeedbackCreate,
    response: Response,
    account: dict = Depends(get_current_account),
    svc: FeedbackService = Depends(get_feedback_service),
):
    """POST /tickets/{tid}/feedback — 201 first submission, 200 on replace."""
    with flow_operation(
        "feedback.submit",
        operation="feedback.submit",
        method="POST",
        path=f"/api/tickets/{tid}/feedback",
    ) as op:
        result, created = svc.submit(
            tid,
            user_id=acting_user_id(account, payload.user_id),
            rating=payload.rating,
            comment=payload.comment,
        )
        op["ticket_ref"] = result.get("ticketId")
        response.status_code = 201 if created else 200
        return result


@router.get("/tickets/{tid}/feedback")
def get_feedback(
    tid: str,
    userId: Optional[str] = None,
    account: dict = Depends(get_current_account),
    svc: FeedbackService = Depends(get_feedback_service),
):
    """GET /tickets/{tid}/feedback — read-side rule: the ticket's employee or
    any HR agent. The caller identity is the bearer token (a claimed userId
    that disagrees is a forgery → 403)."""
    with flow_operation(
        "feedback.get",
        operation="feedback.get",
        method="GET",
        path=f"/api/tickets/{tid}/feedback",
    ) as op:
        result = svc.get(tid, user_id=acting_user_id(account, userId))
        op["ticket_ref"] = result.get("ticketId")
        return result
