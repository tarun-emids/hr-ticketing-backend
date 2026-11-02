"""Deliver password-reset OTPs through the local Mailpit SMTP endpoint."""

import smtplib
from email.message import EmailMessage

from fastapi import HTTPException

from app import config
from app.resilience import CircuitOpenError, MailDeliveryError, mail_breaker


def send_password_reset_otp(email: str, otp: str) -> None:
    message = EmailMessage()
    message["Subject"] = "HR Desk password reset code"
    message["From"] = config.MAILPIT_FROM
    message["To"] = email
    message.set_content(
        f"Your HR Desk password reset code is {otp}. "
        f"It expires in {config.PASSWORD_RESET_OTP_TTL_SECONDS // 60} minutes."
    )

    def deliver() -> None:
        try:
            with smtplib.SMTP(
                config.MAILPIT_HOST,
                config.MAILPIT_PORT,
                timeout=config.MAILPIT_TIMEOUT_SECONDS,
            ) as smtp:
                smtp.send_message(message)
        except (OSError, TimeoutError, smtplib.SMTPException):
            raise MailDeliveryError() from None

    try:
        mail_breaker.call(deliver)
    except (CircuitOpenError, MailDeliveryError):
        raise HTTPException(
            status_code=503,
            detail="Password reset email is temporarily unavailable.",
        ) from None
