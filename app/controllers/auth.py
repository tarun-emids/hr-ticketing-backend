"""Authentication endpoints backed by provisioned PostgreSQL password hashes.

Login observability includes no email, password, or credential material.
"""

from fastapi import APIRouter, Depends

from app.deps import get_auth_service_with_reset, get_current_account
from app.models import (
    LoginRequest,
    PasswordChange,
    PasswordResetComplete,
    PasswordResetRequest,
)
from app.observability import flow_operation
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
def login(payload: LoginRequest, svc: AuthService = Depends(get_auth_service_with_reset)):
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


@router.post("/auth/forgot-password", status_code=202)
def forgot_password(
    payload: PasswordResetRequest,
    svc: AuthService = Depends(get_auth_service_with_reset),
):
    """Send an OTP via Mailpit without confirming whether an account exists."""
    svc.request_password_reset(payload.email)
    return {"message": "If an account exists, a reset code has been sent."}


@router.post("/auth/reset-password")
def reset_password(
    payload: PasswordResetComplete,
    svc: AuthService = Depends(get_auth_service_with_reset),
):
    svc.reset_password(payload.email, payload.otp, payload.new_password)
    return {"message": "Password reset successfully. Please sign in again."}


@router.post("/auth/password")
def change_password(
    payload: PasswordChange,
    account: dict = Depends(get_current_account),
    svc: AuthService = Depends(get_auth_service_with_reset),
):
    svc.change_password(account, payload.current_password, payload.new_password)
    return {"message": "Password changed successfully. Please sign in again."}
