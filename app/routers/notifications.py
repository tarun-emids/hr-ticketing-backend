"""DEPRECATED — moved to app/controllers/notifications.py
+ app/services/notification_service.py + app/repositories/notification_repository.py.
Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.notifications no longer exports {name!r} — see app/controllers/notifications.py"
    )
