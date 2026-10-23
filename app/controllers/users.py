"""Users + static meta endpoints.

Observability: ``users.list`` / ``users.agents`` / ``users.meta``
started/completed events with row counts. Names/emails live in the API
responses by necessity but never in the logs — counts and ids only.
"""

from fastapi import APIRouter, Depends

from app.deps import get_user_service
from app.observability import flow_operation
from app.services.user_service import UserService

router = APIRouter(tags=["users"])


@router.get("/users")
def list_users(svc: UserService = Depends(get_user_service)):
    with flow_operation(
        "users.list",
        operation="users.list",
        method="GET",
        path="/api/users",
    ) as op:
        result = svc.list_users()
        op["count"] = len(result)
        return result


@router.get("/users/agents")
def list_agents(svc: UserService = Depends(get_user_service)):
    with flow_operation(
        "users.agents",
        operation="users.agents",
        method="GET",
        path="/api/users/agents",
    ) as op:
        result = svc.list_agents()
        op["count"] = len(result)
        return result


@router.get("/meta")
def meta(svc: UserService = Depends(get_user_service)):
    with flow_operation(
        "users.meta",
        operation="users.meta",
        method="GET",
        path="/api/meta",
    ):
        return svc.meta()
