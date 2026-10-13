"""Password hashing helpers for organisation-provisioned HR Desk accounts."""

import base64
import hashlib
import hmac
import os

_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${encode(salt)}${encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, raw_salt, raw_digest = encoded.split("$", 5)
        if (
            algorithm != "scrypt"
            or int(raw_n) != _SCRYPT_N
            or int(raw_r) != _SCRYPT_R
            or int(raw_p) != _SCRYPT_P
        ):
            return False

        def decode(value: str) -> bytes:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

        salt = decode(raw_salt)
        expected = decode(raw_digest)
        if len(salt) != _SALT_BYTES or len(expected) != _KEY_BYTES:
            return False
    except AttributeError, ValueError:
        return False
    actual = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )
    return hmac.compare_digest(actual, expected)
