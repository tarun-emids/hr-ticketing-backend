"""Admin console APIs — one app, one file per concern.

    guards.py       authorization: admin gate + self-or-admin rule for metrics
    repository.py   SQL: account admin, KB document admin, ticket row scan
    analytics.py    pure rules: period windows, KPI/category/repetition math,
                    per-agent metrics + bucketed chart series
    accounts.py     create accounts, change roles (promote/demote), delete
    kb_docs.py      upload / edit / delete knowledge-base documents (+ chunk
                    refresh), using app/rag for citable paragraph derivation
    controller.py   HTTP faces under /admin (plus self /admin/metrics)

Role model: `public.users.role` gains the 'admin' value (schema.sql). Admin
endpoints carry actorId and re-resolve the role server-side — the RBAC trust
anchor stays exactly the account row, like every other surface here.
"""
