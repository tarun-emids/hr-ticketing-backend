"""DEPRECATED — the whole notification domain lives in
app/services/notification_service.py (pure recipient/message rules at module
level, NotificationService for emit + SLA/retention jobs) and
app/repositories/notification_repository.py for the queries.
Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.notifications no longer exports {name!r} — see app/services/notification_service.py"
    )
