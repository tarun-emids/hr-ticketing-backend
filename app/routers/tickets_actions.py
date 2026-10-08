"""DEPRECATED — status/priority/category/assignee moved into
app/controllers/tickets.py + app/services/ticket_service.py. Delete when
convenient."""


def __getattr__(name):
    raise ImportError(
        f"app.routers.tickets_actions no longer exports {name!r} — see app/controllers/tickets.py"
    )
