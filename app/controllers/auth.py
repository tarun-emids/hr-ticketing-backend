"""Authentication endpoints backed by provisioned PostgreSQL password hashes.

Login observability includes no email, password, or credential material.
"""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service
from app.models import LoginRequest
from app.observability import flow_operation
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, svc: AuthService = Depends(get_auth_service)):
    """POST /api/auth/login — verify credentials and return the app user."""
    with flow_operation(
        "auth.login",
        operation="auth.login",
        method="POST",
        path="/api/auth/login",
    ) as op:
        result = svc.login(payload.email, payload.password)
        op["user_id"] = result["user"]["id"]
        return result
