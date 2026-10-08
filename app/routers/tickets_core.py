"""DEPRECATED — logic split into app/controllers/tickets.py,
app/services/ticket_service.py and app/repositories/ticket_repository.py.
Delete when convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.tickets_core no longer exports {name!r} — see app/controllers/tickets.py"
    )
