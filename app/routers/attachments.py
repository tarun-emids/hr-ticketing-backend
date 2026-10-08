"""DEPRECATED — moved to app/controllers/attachments.py
+ app/services/ticket_service.py (upload/URL) + app/repositories/attachment_storage.py.
Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.attachments no longer exports {name!r} — see app/controllers/attachments.py"
    )
