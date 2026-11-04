"""Authentication endpoints backed by provisioned PostgreSQL password hashes.

Login observability includes no email, password, or credential material.
"""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service
from app.models import ForgotPasswordRequest, LoginRequest, ResetPasswordRequest
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


@router.post("/auth/forgot-password")
def forgot_password(
    payload: ForgotPasswordRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """Request a time-limited password reset code by email."""
    with flow_operation(
        "auth.password_reset.request",
        operation="auth.password_reset.request",
        method="POST",
        path="/api/auth/forgot-password",
    ):
        return svc.request_password_reset(payload.email)


@router.post("/auth/reset-password")
def reset_password(
    payload: ResetPasswordRequest,
    svc: AuthService = Depends(get_auth_service),
):
    """Set a new password with a valid one-time reset code."""
    with flow_operation(
        "auth.password_reset.complete",
        operation="auth.password_reset.complete",
        method="POST",
        path="/api/auth/reset-password",
    ):
        return svc.reset_password(payload.email, payload.otp, payload.new_password)
