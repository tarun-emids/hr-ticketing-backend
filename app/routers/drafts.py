"""DEPRECATED — moved to app/controllers/drafts.py + app/services/draft_service.py
+ app/repositories/draft_repository.py. Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.drafts no longer exports {name!r} — see app/controllers/drafts.py"
    )
