"""Admin console endpoints (every call re-verifies the acting account).

Faces:
    GET/POST/PATCH/DELETE /admin/kb/documents[/{slug}]      KB document admin
    GET/POST /admin/accounts · PATCH accounts/{id}/role · DELETE accounts/{id}
    GET /admin/analytics/overview?window= ·  GET /admin/analytics/agents?period=
    GET /admin/metrics/agents/{agent_id}?period=            agent drill-down

`actorId` travels like every other acting-id in this app (query/body) and is
resolved server-side — see app/admin/guards.py. Authorization happens HERE,
at the HTTP edge, once per request; services stay pure business logic.
"""

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.admin.accounts import AdminAccountService
from app.admin.analytics import DEFAULT_PERIOD
from app.admin.analytics_service import AdminAnalyticsService
from app.admin.guards import require_admin
from app.admin.kb_docs import AdminKbDocService
from app.deps import (
    get_admin_account_service,
    get_admin_analytics_service,
    get_admin_kb_service,
    get_user_repo,
)
from app.models import AccountCreate, AccountRoleUpdate
from app.repositories.user_repository import UserRepository

router = APIRouter(prefix="/admin", tags=["admin"])


# -- analytics ----------------------------------------------------------------


@router.get("/analytics/overview")
def analytics_overview(
    actorId: str,
    window: str = Query("all", pattern="^(all|24h|7d|30d)$"),
    svc: AdminAnalyticsService = Depends(get_admin_analytics_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Org-wide ticket analytics: fine counts, response/solve distributions,
    category load + repetitive-subject clusters (the KB-improvement signal)."""
    require_admin(users, actorId)
    return svc.overview(window=window)


@router.get("/analytics/agents")
def analytics_leaderboard(
    actorId: str,
    period: str = Query(DEFAULT_PERIOD, pattern="^(24h|7d|30d)$"),
    svc: AdminAnalyticsService = Depends(get_admin_analytics_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Top-performing agents for the period (completed desc)."""
    require_admin(users, actorId)
    return svc.leaderboard(period=period)


@router.get("/metrics/agents/{agent_id}")
def agent_metrics(
    agent_id: str,
    actorId: str,
    period: str = Query(DEFAULT_PERIOD, pattern="^(24h|7d|30d)$"),
    svc: AdminAnalyticsService = Depends(get_admin_analytics_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Individual performance drill-down — admins query any agent, agents
    only themselves (the HR dashboard's personal view reuses this)."""
    return svc.agent_drilldown(actor_id=actorId, target_id=agent_id, period=period)


# -- accounts ---------------------------------------------------------------


@router.get("/accounts")
def list_accounts(
    actorId: str,
    svc: AdminAccountService = Depends(get_admin_account_service),
    users: UserRepository = Depends(get_user_repo),
):
    require_admin(users, actorId)
    return svc.list_accounts()


@router.post("/accounts", status_code=201)
def create_account(
    actorId: str,
    body: AccountCreate,
    svc: AdminAccountService = Depends(get_admin_account_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Create one account (name/email/role/password) — onboarding without psql."""
    require_admin(users, actorId)
    return svc.create(
        name=body.name, email=body.email, role=body.role, password=body.password
    )


@router.patch("/accounts/{account_id}/role")
def change_role(
    account_id: str,
    actorId: str,
    body: AccountRoleUpdate,
    svc: AdminAccountService = Depends(get_admin_account_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Promote/demote an account (employee <-> agent <-> admin)."""
    require_admin(users, actorId)
    return svc.set_role(account_id, body.role)


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: str,
    actorId: str,
    svc: AdminAccountService = Depends(get_admin_account_service),
    users: UserRepository = Depends(get_user_repo),
):
    require_admin(users, actorId)
    return svc.delete(account_id)


# -- knowledge-base documents ---------------------------------------------------


@router.get("/kb/documents")
def list_kb_documents(
    actorId: str,
    svc: AdminKbDocService = Depends(get_admin_kb_service),
    users: UserRepository = Depends(get_user_repo),
):
    require_admin(users, actorId)
    return svc.list_documents()


@router.post("/kb/documents", status_code=201)
def create_kb_document(
    actorId: str,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form("General"),
    audience: str = Form("employee"),
    summary: str = Form(""),
    keywords: str = Form(""),
    version: str = Form("v1.0"),
    effectiveDate: str = Form(""),
    svc: AdminKbDocService = Depends(get_admin_kb_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Upload a new policy PDF (multipart). Assistant paragraphs refresh when
    the embeddings key is configured."""
    require_admin(users, actorId)
    return svc.create(
        title=title,
        category=category,
        audience=audience,
        summary=summary,
        keywords=keywords,
        version=version,
        effective_date=effectiveDate,
        filename=file.filename or "",
        data=file.file.read(),
    )


@router.patch("/kb/documents/{slug}")
def update_kb_document(
    slug: str,
    actorId: str,
    file: UploadFile | None = File(None),
    title: str | None = Form(None),
    category: str | None = Form(None),
    audience: str | None = Form(None),
    summary: str | None = Form(None),
    keywords: str | None = Form(None),
    version: str | None = Form(None),
    effectiveDate: str | None = Form(None),
    svc: AdminKbDocService = Depends(get_admin_kb_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Edit metadata and/or replace the PDF; replacing re-cuts citations."""
    require_admin(users, actorId)
    return svc.update(
        slug,
        title=title,
        category=category,
        audience=audience,
        summary=summary,
        keywords=keywords,
        version=version,
        effective_date=effectiveDate,
        filename=(file.filename if file else None),
        data=(file.file.read() if file else None),
    )


@router.delete("/kb/documents/{slug}")
def delete_kb_document(
    slug: str,
    actorId: str,
    svc: AdminKbDocService = Depends(get_admin_kb_service),
    users: UserRepository = Depends(get_user_repo),
):
    """Delete a policy; its assistant citation chunks cascade with it."""
    require_admin(users, actorId)
    return svc.delete(slug)
