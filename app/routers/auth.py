"""DEPRECATED — moved to app/controllers/auth.py + app/services/auth_service.py.
Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.auth no longer exports {name!r} — see app/controllers/auth.py"
    )
