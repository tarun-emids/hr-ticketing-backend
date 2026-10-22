"""Dependency-injection wiring (FastAPI Depends graph).

    controller --Depends--> service --Depends--> repository --Depends--> PostgreSQL

The pool is resolved here via `app.config.get_database()` at call time
(module attribute, not a from-import binding): tests monkeypatch
`app.config.get_database` to inject the offline database for every request
and every repository in one place.
"""

from fastapi import Depends

from app import config as app_config
from app.repositories.attachment_storage import AttachmentStorageRepository
from app.repositories.draft_repository import DraftRepository
from app.repositories.kb_repository import KbRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.draft_service import DraftService
from app.services.kb_service import KbService
from app.services.log_ingest_service import LogIngestService
from app.services.notification_service import NotificationService
from app.services.ticket_service import TicketService
from app.services.user_service import UserService


def get_database():
    """Shared PostgreSQL connection pool."""
    return app_config.get_database()


# -- repositories ---------------------------------------------------------


def get_user_repo(database=Depends(get_database)) -> UserRepository:
    return UserRepository(database)


def get_ticket_repo(database=Depends(get_database)) -> TicketRepository:
    return TicketRepository(database)


def get_draft_repo(database=Depends(get_database)) -> DraftRepository:
    return DraftRepository(database)


def get_notification_repo(database=Depends(get_database)) -> NotificationRepository:
    return NotificationRepository(database)


def get_storage_repo(database=Depends(get_database)) -> AttachmentStorageRepository:
    return AttachmentStorageRepository(database)


def get_kb_repo(database=Depends(get_database)) -> KbRepository:
    return KbRepository(database)


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


def get_auth_service(users: UserRepository = Depends(get_user_repo)) -> AuthService:
    return AuthService(users)


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
) -> KbService:
    return KbService(kb, users)
