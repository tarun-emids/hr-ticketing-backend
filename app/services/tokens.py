"""Short-lived HS256 bearer tokens for authenticated API sessions."""

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException

from app import config


def _key() -> bytes:
    key = config.AUTH_SIGNING_KEY or config.ATTACHMENT_SIGNING_KEY
    encoded = key.encode("utf-8")
    if len(encoded) < 32:
        raise HTTPException(
            status_code=503,
            detail="Authentication signing key is not configured.",
        )
    return encoded


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def create_access_token(account: dict) -> str:
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(
        json.dumps(
            {
                "sub": str(account["id"]),
                "ver": int(account.get("auth_version") or 0),
                "iat": now,
                "exp": now + config.AUTH_TOKEN_TTL_SECONDS,
            },
            separators=(",", ":"),
        ).encode("utf-8")
    )
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(_key(), signing_input, hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        header_part, payload_part, signature_part = token.split(".")

        def decode(value: str) -> bytes:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

        header = json.loads(decode(header_part))
        payload = json.loads(decode(payload_part))
        expected = hmac.new(
            _key(), f"{header_part}.{payload_part}".encode("ascii"), hashlib.sha256
        ).digest()
        if (
            header != {"alg": "HS256", "typ": "JWT"}
            or not hmac.compare_digest(expected, decode(signature_part))
            or not isinstance(payload.get("sub"), str)
            or not isinstance(payload.get("ver"), int)
            or not isinstance(payload.get("exp"), int)
            or payload["exp"] <= int(time.time())
        ):
            raise ValueError("Invalid token")
        return payload
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token.") from None
