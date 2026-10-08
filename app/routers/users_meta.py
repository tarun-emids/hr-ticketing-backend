"""DEPRECATED — moved to app/controllers/users.py + app/services/user_service.py
+ app/repositories/user_repository.py. Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.users_meta no longer exports {name!r} — see app/controllers/users.py"
    )
