"""Feedback endpoints."""

from fastapi import APIRouter, Depends, Response

from app.deps import get_feedback_service
from app.models import FeedbackCreate
from app.observability import flow_operation
from app.services.feedback_service import FeedbackService

router = APIRouter(tags=["feedback"])


@router.post("/tickets/{tid}/feedback")
def submit_feedback(
    tid: str,
    payload: FeedbackCreate,
    response: Response,
    svc: FeedbackService = Depends(get_feedback_service),
):
    """POST /tickets/{tid}/feedback - 201 on the first submission, 200 when it
    replaces an existing one."""
    with flow_operation(
        "feedback.submit",
        operation="feedback.submit",
        method="POST",
        path=f"/api/tickets/{tid}/feedback",
    ) as op:
        result, created = svc.submit(
            tid,
            user_id=payload.user_id,
            rating=payload.rating,
            comment=payload.comment,
        )
        op["ticket_ref"] = result.get("ticketId")
        response.status_code = 201 if created else 200
        return result


@router.get("/tickets/{tid}/feedback")
def get_feedback(tid: str, userId: str, svc: FeedbackService = Depends(get_feedback_service)):
    """GET /tickets/{tid}/feedback - read-side rule: the ticket's employee or
    any HR agent. Caller identity rides the userId query parameter, mirroring
    the drafts/notification reads."""
    with flow_operation(
        "feedback.get",
        operation="feedback.get",
        method="GET",
        path=f"/api/tickets/{tid}/feedback",
    ) as op:
        result = svc.get(tid, user_id=userId)
        op["ticket_ref"] = result.get("ticketId")
        return result
