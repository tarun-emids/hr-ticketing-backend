"""Database-backed password authentication tests."""

import pytest
from fastapi import HTTPException

from app.services.auth_service import AuthService, clean_email
from app.services.passwords import hash_password, verify_password


def test_password_hashes_verify_without_storing_plaintext():
    password = "an-initial-password-that-is-long"
    encoded = hash_password(password)

    assert encoded != password
    assert verify_password(password, encoded)
    assert not verify_password("different-password", encoded)
    assert not verify_password(password, "invalid-hash")


def test_login_returns_public_user_without_password_hash():
    password_hash = hash_password("a-long-provisioned-password")
    user = {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": "Ada Example",
        "email": "ada@example.com",
        "role": "employee",
        "password_hash": password_hash,
    }

    class Users:
        def get_credentials_by_email(self, email):
            assert email == "ada@example.com"
            return user

    response = AuthService(Users()).login(" ADA@example.com ", "a-long-provisioned-password")
    assert response == {
        "user": {key: value for key, value in user.items() if key != "password_hash"}
    }


@pytest.mark.parametrize(
    ("row", "password"),
    [
        (None, "wrong"),
        ({"password_hash": None}, "wrong"),
        ({"password_hash": hash_password("correct-password")}, "wrong"),
    ],
)
def test_login_returns_generic_error_for_missing_or_invalid_credentials(row, password):
    class Users:
        def get_credentials_by_email(self, _email):
            return row

    with pytest.raises(HTTPException) as error:
        AuthService(Users()).login("nobody@example.com", password)
    assert error.value.status_code == 401
    assert error.value.detail == "Invalid email or password."


def test_clean_email_strips_invisible_whitespace():
    assert clean_email("  Ada\u200b@Example.com\u00a0") == "ada@example.com"
