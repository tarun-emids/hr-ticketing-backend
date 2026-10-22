"""Authentication endpoints backed by provisioned PostgreSQL password hashes."""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service
from app.models import LoginRequest
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    """POST /api/auth/login — verify credentials and return the app user."""
    return svc.login(payload.email, payload.password)
