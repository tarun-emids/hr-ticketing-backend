"""Users + static meta endpoints."""

from fastapi import APIRouter, Depends

from app.deps import get_user_service
from app.services.user_service import UserService

router = APIRouter(tags=["users"])


@router.get("/users")
def list_users(svc: UserService = Depends(get_user_service)):
    return svc.list_users()


@router.get("/users/agents")
def list_agents(svc: UserService = Depends(get_user_service)):
    return svc.list_agents()


@router.get("/meta")
def meta(svc: UserService = Depends(get_user_service)):
    return svc.meta()
