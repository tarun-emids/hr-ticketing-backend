"""Auth endpoints. The GoTrue grant + account join live in AuthService.

Observability: the login operation emits ``auth.login.started/failed/completed``
(hrdesk.flow). NEVER logged: the email, the password, GoTrue tokens, or any
credential material — diagnosis uses only the mapped HTTP status on the
failed record (401 wrong credentials, 403 unconfirmed account / no account
row, 502 authentication service unreachable) and the exception class. On
success only the verified user's UUID is attached.
"""
from fastapi import APIRouter, Depends

from app.deps import get_auth_service
from app.models import LoginRequest
from app.observability import flow_operation
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    """POST /api/auth/login — real password sign-in (GoTrue password grant,
    then resolve the public.users row for the app-level id/name/role)."""
    with flow_operation(
        "auth.login",
        operation="auth.login",
        method="POST",
        path="/api/auth/login",
    ) as op:
        result = svc.login(payload.email, payload.password)
        op["user_id"] = (result.get("user") or {}).get("id")
        return result
