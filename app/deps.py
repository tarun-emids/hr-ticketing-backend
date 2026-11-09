"""Dependency-injection wiring (FastAPI Depends graph).

    controller --Depends--> service --Depends--> repository --Depends--> PostgreSQL

The pool is resolved here via `app.config.get_database()` at call time
(module attribute, not a from-import binding): tests monkeypatch
`app.config.get_database` to inject the offline database for every request
and every repository in one place.
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg_pool import ConnectionPool

from app import config as app_config
from app.admin.accounts import AdminAccountService
from app.admin.analytics_service import AdminAnalyticsService
from app.admin.kb_docs import AdminKbDocService
from app.admin.repository import AdminRepository
from app.cache import TtlCache
from app.rag.repository import RagRepository
from app.rag.service import RagService
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.repositories.draft_repository import DraftRepository
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.kb_repository import KbRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.password_reset_repository import PasswordResetRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.draft_service import DraftService
from app.services.feedback_service import FeedbackService
from app.services.kb_service import KbService
from app.services.log_ingest_service import LogIngestService
from app.services.notification_service import NotificationService
from app.services.ticket_service import TicketService
from app.services.tokens import decode_access_token
from app.services.user_service import UserService


def get_database():
    """Shared PostgreSQL connection pool."""
    return app_config.get_database()


def get_kb_cache() -> TtlCache:
    """Shared knowledge base metadata cache."""
    return app_config.get_kb_cache()


# -- repositories ---------------------------------------------------------


def get_user_repo(database: ConnectionPool = Depends(get_database)) -> UserRepository:
    return UserRepository(database)


def get_ticket_repo(database: ConnectionPool = Depends(get_database)) -> TicketRepository:
    return TicketRepository(database)


def get_draft_repo(database: ConnectionPool = Depends(get_database)) -> DraftRepository:
    return DraftRepository(database)


def get_notification_repo(
    database: ConnectionPool = Depends(get_database),
) -> NotificationRepository:
    return NotificationRepository(database)


def get_storage_repo(
    database: ConnectionPool = Depends(get_database),
) -> AttachmentStorageRepository:
    return AttachmentStorageRepository(database)


def get_kb_repo(database: ConnectionPool = Depends(get_database)) -> KbRepository:
    return KbRepository(database)


def get_feedback_repo(
    database: ConnectionPool = Depends(get_database),
) -> FeedbackRepository:
    return FeedbackRepository(database)


# -- services ---------------------------------------------------------------


def get_notification_service(
    notifications: NotificationRepository = Depends(get_notification_repo),
    users: UserRepository = Depends(get_user_repo),
    tickets: TicketRepository = Depends(get_ticket_repo),
) -> NotificationService:
    return NotificationService(notifications, users, tickets)


def get_ticket_service(
    storage: AttachmentStorageRepository = Depends(get_storage_repo),
    tickets: TicketRepository = Depends(get_ticket_repo),
    users: UserRepository = Depends(get_user_repo),
    notifier: NotificationService = Depends(get_notification_service),
) -> TicketService:
    return TicketService(tickets, users, notifier, storage)


def get_user_service(users: UserRepository = Depends(get_user_repo)) -> UserService:
    return UserService(users)


def get_password_reset_repo(
    database: ConnectionPool = Depends(get_database),
) -> PasswordResetRepository:
    return PasswordResetRepository(database)


def get_auth_service_with_reset(
    users: UserRepository = Depends(get_user_repo),
    resets: PasswordResetRepository = Depends(get_password_reset_repo),
) -> AuthService:
    return AuthService(users, resets)


_bearer = HTTPBearer(auto_error=False)


def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    users: UserRepository = Depends(get_user_repo),
) -> dict:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authentication required.")
    token = decode_access_token(credentials.credentials)
    account = users.get_by_id(token["sub"])
    if not account or int(account.get("auth_version") or 0) != token["ver"]:
        raise HTTPException(status_code=401, detail="Invalid or expired access token.")
    return account


def get_current_admin(account: dict = Depends(get_current_account)) -> dict:
    if account.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return account


def get_current_agent(account: dict = Depends(get_current_account)) -> dict:
    """Staff-route guard: HR agents, plus admins working the console paths,
    who share the agent workflow surface (assign/status/priority/auto-assign)."""
    if account.get("role") not in ("agent", "admin"):
        raise HTTPException(status_code=403, detail="Agent access required.")
    return account


def acting_user_id(account: dict, claimed: str | None = None) -> str:
    """The data-subject id, derived from the bearer token.

    A client-supplied id is honoured only when it AGREES with the token —
    anything else is an identity forgery attempt and is rejected (403), not
    silently used. Query/body params stay optional so callers may keep
    sending them; the token wins either way.
    """
    if claimed and claimed != str(account["id"]):
        raise HTTPException(
            status_code=403,
            detail="The acting user is fixed by your bearer token.",
        )
    return str(account["id"])


def employee_scoped_id(account: dict, claimed: str | None = None) -> str | None:
    """employeeId-style LIST FILTERS, for ticket listings.

    Employees are hard-scoped to themselves — the filter is forced to the
    token identity (even when the client sent none, an employee can only
    ever see their own tickets). Agents/admins may filter by anyone, or by
    none to list across the whole directory.
    """
    if account.get("role") != "employee":
        return claimed
    if claimed and claimed != str(account["id"]):
        raise HTTPException(
            status_code=403,
            detail="Employees may only list their own tickets.",
        )
    return str(account["id"])


def get_draft_service(
    drafts: DraftRepository = Depends(get_draft_repo),
    tickets: TicketRepository = Depends(get_ticket_repo),
    users: UserRepository = Depends(get_user_repo),
    storage: AttachmentStorageRepository = Depends(get_storage_repo),
    notifier: NotificationService = Depends(get_notification_service),
) -> DraftService:
    return DraftService(drafts, tickets, users, storage, notifier)


def get_log_ingest_service() -> LogIngestService:
    """Frontend log sink (writes through the logging system)."""
    return LogIngestService()


def get_kb_service(
    kb: KbRepository = Depends(get_kb_repo),
    users: UserRepository = Depends(get_user_repo),
    cache: TtlCache = Depends(get_kb_cache),
) -> KbService:
    return KbService(kb, users, cache)


def get_feedback_service(
    feedbacks: FeedbackRepository = Depends(get_feedback_repo),
    tickets: TicketRepository = Depends(get_ticket_repo),
    users: UserRepository = Depends(get_user_repo),
) -> FeedbackService:
    return FeedbackService(feedbacks, tickets, users)


# -- HR assistant (app/rag) ---------------------------------------------------


def get_rag_repo(database=Depends(get_database)) -> RagRepository:
    return RagRepository(database)


def get_rag_service(
    rag: RagRepository = Depends(get_rag_repo),
    users: UserRepository = Depends(get_user_repo),
) -> RagService:
    return RagService(rag, users)


# -- Admin console (app/admin) --------------------------------------------------


def get_admin_repo(database=Depends(get_database)) -> AdminRepository:
    return AdminRepository(database)


def get_admin_account_service(
    repo: AdminRepository = Depends(get_admin_repo),
    users: UserRepository = Depends(get_user_repo),
) -> AdminAccountService:
    return AdminAccountService(repo, users)


def get_admin_kb_service(
    repo: AdminRepository = Depends(get_admin_repo),
    cache: TtlCache = Depends(get_kb_cache),
) -> AdminKbDocService:
    return AdminKbDocService(repo, cache)


def get_admin_analytics_service(
    repo: AdminRepository = Depends(get_admin_repo),
    users: UserRepository = Depends(get_user_repo),
) -> AdminAnalyticsService:
    return AdminAnalyticsService(repo, users)
