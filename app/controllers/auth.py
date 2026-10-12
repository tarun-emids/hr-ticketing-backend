"""Auth endpoints. The GoTrue grant + account join live in AuthService."""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service
from app.models import LoginRequest
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    """POST /api/auth/login — real password sign-in (GoTrue password grant,
    then resolve the public.users row for the app-level id/name/role)."""
    return svc.login(payload.email, payload.password)
