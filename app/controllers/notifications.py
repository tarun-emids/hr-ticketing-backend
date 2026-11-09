"""In-app notifications endpoints.

Every endpoint is scoped by the acting user (`userId`): the service queries below are hard-scoped to rows
whose recipient_id equals that user — there is no way to read or mark
someone else's notifications through this controller.

Input validation (state / limit / offset bounds) stays at the edge; the
service enforces data isolation.

Observability: list/read/read-all/sweep get the standard
``notifications.*`` started/completed/failed events with safe metadata
(counts, the acting user's UUID, notification UUID). The one DELIBERATE
exception is ``GET /notifications/unread-count`` — the frontend bell polls
it every ~20 s (``src/hooks.js useNotifications``), so instrumenting it
would flood the log; the per-request middleware line already covers it.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.deps import acting_user_id, get_current_account, get_notification_service
from app.models import NotificationRead
from app.observability import flow_operation
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])

MAX_PAGE = 100


@router.get("")
def list_notifications(
    userId: Optional[str] = None,
    state: str = "all",
    limit: int = 20,
    offset: int = 0,
    account: dict = Depends(get_current_account),
    svc: NotificationService = Depends(get_notification_service),
):
    """GET /notifications?userId=&state=unread&limit=20&offset= — newest-first,
    hard-scoped to the acting user (chronological, not unread-first). The
    recipient comes from the bearer token; a client userId that disagrees is
    rejected."""
    userId = acting_user_id(account, userId)
    svc.require_user(userId)
    if state not in ("all", "unread"):
        raise HTTPException(status_code=422, detail="state must be 'all' or 'unread'")
    if limit < 1 or limit > MAX_PAGE:
        raise HTTPException(status_code=422, detail=f"limit must be 1..{MAX_PAGE}")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be >= 0")

    with flow_operation(
        "notifications.list",
        operation="notifications.list",
        method="GET",
        path="/api/notifications",
        user_id=userId,
        state=state,
        limit=limit,
        offset=offset,
    ) as op:
        result = svc.list_notifications(
            userId, unread_only=(state == "unread"), limit=limit, offset=offset
        )
        op["count"] = len(result)
        return result


@router.get("/unread-count")
def unread_count(
    userId: Optional[str] = None,
    account: dict = Depends(get_current_account),
    svc: NotificationService = Depends(get_notification_service),
):
    userId = acting_user_id(account, userId)
    svc.require_user(userId)
    return {"unread": svc.unread_count(userId)}


@router.post("/read-all")
def mark_all_read(
    body: NotificationRead,
    account: dict = Depends(get_current_account),
    svc: NotificationService = Depends(get_notification_service),
):
    user_id = acting_user_id(account, body.user_id)
    svc.require_user(user_id)
    with flow_operation(
        "notifications.mark_all_read",
        operation="notifications.mark_all_read",
        method="POST",
        path="/api/notifications/read-all",
        user_id=user_id,
    ) as op:
        updated = svc.mark_all_read(user_id)
        op["updated"] = updated
        return {"updated": updated}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: str,
    body: NotificationRead,
    account: dict = Depends(get_current_account),
    svc: NotificationService = Depends(get_notification_service),
):
    user_id = acting_user_id(account, body.user_id)
    svc.require_user(user_id)
    with flow_operation(
        "notifications.mark_read",
        operation="notifications.mark_read",
        method="POST",
        path=f"/api/notifications/{notification_id}/read",
        user_id=user_id,
    ) as op:
        op["notification_id"] = notification_id
        return svc.mark_read(notification_id, user_id)


@router.post("/sweep")
def sweep(
    body: NotificationRead,
    account: dict = Depends(get_current_account),
    svc: NotificationService = Depends(get_notification_service),
):
    """Manually run the SLA sweep + retention cleanup — the same calls the
    background scheduler makes every 30 minutes; here for ops/test rigs."""
    user_id = acting_user_id(account, body.user_id)
    svc.require_user(user_id)
    with flow_operation(
        "notifications.sweep",
        operation="notifications.sweep",
        method="POST",
        path="/api/notifications/sweep",
        user_id=user_id,
    ) as op:
        sla_notified = svc.run_sla_sweep()
        deleted = svc.run_retention_cleanup()
        op["sla_notified"] = sla_notified
        op["deleted"] = deleted
        return {"slaNotified": sla_notified, "deleted": deleted}
