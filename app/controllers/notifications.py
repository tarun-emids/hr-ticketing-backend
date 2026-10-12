"""In-app notifications endpoints.

Every endpoint is scoped by the acting user (`userId`, the mock-auth
stand-in for a token): the service queries below are hard-scoped to rows
whose recipient_id equals that user — there is no way to read or mark
someone else's notifications through this controller.

Input validation (state / limit / offset bounds) stays at the edge; the
service enforces data isolation.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.deps import get_notification_service
from app.models import NotificationRead
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])

MAX_PAGE = 100


@router.get("")
def list_notifications(
    userId: str,
    state: str = "all",
    limit: int = 20,
    offset: int = 0,
    svc: NotificationService = Depends(get_notification_service),
):
    """GET /notifications?userId=&state=unread&limit=20&offset= — newest-first,
    hard-scoped to the acting user (chronological, not unread-first)."""
    svc.require_user(userId)
    if state not in ("all", "unread"):
        raise HTTPException(status_code=422, detail="state must be 'all' or 'unread'")
    if limit < 1 or limit > MAX_PAGE:
        raise HTTPException(status_code=422, detail=f"limit must be 1..{MAX_PAGE}")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be >= 0")

    return svc.list_notifications(
        userId, unread_only=(state == "unread"), limit=limit, offset=offset
    )


@router.get("/unread-count")
def unread_count(userId: str, svc: NotificationService = Depends(get_notification_service)):
    svc.require_user(userId)
    return {"unread": svc.unread_count(userId)}


@router.post("/read-all")
def mark_all_read(
    body: NotificationRead, svc: NotificationService = Depends(get_notification_service)
):
    svc.require_user(body.user_id)
    return {"updated": svc.mark_all_read(body.user_id)}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: str,
    body: NotificationRead,
    svc: NotificationService = Depends(get_notification_service),
):
    svc.require_user(body.user_id)
    return svc.mark_read(notification_id, body.user_id)


@router.post("/sweep")
def sweep(body: NotificationRead, svc: NotificationService = Depends(get_notification_service)):
    """Manually run the SLA sweep + retention cleanup — the same calls the
    background scheduler makes every 30 minutes; here for ops/test rigs."""
    svc.require_user(body.user_id)
    return {"slaNotified": svc.run_sla_sweep(), "deleted": svc.run_retention_cleanup()}
