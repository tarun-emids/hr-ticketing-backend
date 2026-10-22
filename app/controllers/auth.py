"""Authentication endpoints backed by provisioned PostgreSQL password hashes.

Observability: the login operation emits ``auth.login.started/failed/completed``
(hrdesk.flow). NEVER logged: the email, the password, or any credential
material — diagnosis uses only the mapped HTTP status on the failed record
(401 wrong credentials) and the exception class. On success only the verified
user's UUID is attached.
"""
from fastapi import APIRouter, Depends

from app.deps import get_auth_service
from app.models import LoginRequest
from app.observability import flow_operation
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    """POST /api/auth/login — verify the stored password hash and return the
    account row (id/name/role) for the app-level session."""
    with flow_operation(
        "auth.login",
        operation="auth.login",
        method="POST",
        path="/api/auth/login",
    ) as op:
        result = svc.login(payload.email, payload.password)
        op["user_id"] = (result.get("user") or {}).get("id")
        return result
