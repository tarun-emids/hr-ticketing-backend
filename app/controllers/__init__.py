"""Controller layer (FastAPI routers) — request parsing + response plumbing.

Controllers contain NO business logic and NO database queries: they bind
URLs/parameters to a service call and return whatever the service hands
back. All rules live in app/services, all data access in app/repositories.
"""
