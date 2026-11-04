"""Bcrypt password hashing for organisation-managed HR Desk accounts."""

import base64
import hashlib
import hmac

import bcrypt

_BCRYPT_ROUNDS = 12
_SCRYPT_N = 1 << 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_BYTES = 32


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if not encoded or len(encoded) > 72:
        raise ValueError("Password must contain between 1 and 72 UTF-8 bytes.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("ascii")


def _verify_scrypt(password: str, encoded: str) -> bool:
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
    except (AttributeError, ValueError):
        return False
    actual = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_KEY_BYTES
    )
    return hmac.compare_digest(actual, expected)


def verify_password(password: str, encoded: str) -> bool:
    if not encoded:
        return False
    if encoded.startswith("scrypt$"):
        return _verify_scrypt(password, encoded)
    try:
        return bcrypt.checkpw(password.encode("utf-8"), encoded.encode("ascii"))
    except (AttributeError, ValueError, UnicodeEncodeError):
        return False
