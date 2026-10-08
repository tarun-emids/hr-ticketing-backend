"""DEPRECATED — auto-assign/workload moved into app/controllers/tickets.py
+ app/services/ticket_service.py. Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.assignment no longer exports {name!r} — see app/controllers/tickets.py"
    )
