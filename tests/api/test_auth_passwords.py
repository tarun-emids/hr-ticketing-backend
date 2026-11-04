"""Authentication tokens and password-reset lifecycle."""

from fastapi import HTTPException

from app.services.passwords import hash_password, verify_password
from tests.conftest import U


def _login(api, password="Initial-password-2026"):
    return api.client.post(
        "/api/auth/login",
        json={"email": "priya@acme.com", "password": password},
    )


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_issues_bearer_and_never_returns_password_hash(api):
    unauthenticated = api.client.get("/api/users", headers={"Authorization": ""})
    assert unauthenticated.status_code == 401

    api.fake.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (hash_password("Initial-password-2026"), U["priya"]),
    )
    response = _login(api)
    assert response.status_code == 200
    result = response.json()
    assert result["tokenType"] == "bearer"
    assert result["expiresIn"] > 0
    assert result["accessToken"]
    assert "password_hash" not in result["user"]

    password_change = api.client.post(
        "/api/auth/password",
        headers=_auth_header(result["accessToken"]),
        json={
            "currentPassword": "Initial-password-2026",
            "newPassword": "Changed-password-2026",
        },
    )
    assert password_change.status_code == 200
    assert verify_password(
        "Changed-password-2026",
        api.fake.execute("SELECT password_hash FROM users WHERE id = %s", (U["priya"],))[0][
            "password_hash"
        ],
    )
    assert (
        api.client.post(
            "/api/auth/password",
            headers=_auth_header(result["accessToken"]),
            json={
                "currentPassword": "Initial-password-2026",
                "newPassword": "Another-password-2026",
            },
        ).status_code
        == 401
    )


def test_forgot_password_otp_is_bcrypt_hashed_and_single_use(api, monkeypatch):
    from app.services import auth_service

    password = "Initial-password-2026"
    api.fake.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s", (hash_password(password), U["priya"])
    )
    issued = {}

    def capture_email(email, otp):
        issued.update({"email": email, "otp": otp})

    monkeypatch.setattr(auth_service, "send_password_reset_otp", capture_email)
    unknown = api.client.post("/api/auth/forgot-password", json={"email": "unknown@example.com"})
    known = api.client.post("/api/auth/forgot-password", json={"email": "PRIYA@acme.com"})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    assert issued["email"] == "priya@acme.com"

    record = api.fake.execute(
        "SELECT otp_hash FROM password_reset_otps WHERE user_id = %s", (U["priya"],)
    )[0]
    assert record["otp_hash"] != issued["otp"]
    assert record["otp_hash"].startswith("$2")
    assert verify_password(issued["otp"], record["otp_hash"])

    reset = api.client.post(
        "/api/auth/reset-password",
        json={
            "email": "priya@acme.com",
            "otp": issued["otp"],
            "newPassword": "Reset-password-2026",
        },
    )
    assert reset.status_code == 200
    assert _login(api, password).status_code == 401
    assert _login(api, "Reset-password-2026").status_code == 200
    assert not api.fake.execute(
        "SELECT user_id FROM password_reset_otps WHERE user_id = %s", (U["priya"],)
    )


def test_reset_otp_is_limited_to_five_attempts(api, monkeypatch):
    from app.services import auth_service

    api.fake.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (hash_password("Initial-password-2026"), U["priya"]),
    )
    issued = {}

    def capture_email(_email, otp):
        issued["otp"] = otp

    monkeypatch.setattr(auth_service, "send_password_reset_otp", capture_email)
    api.client.post("/api/auth/forgot-password", json={"email": "priya@acme.com"})
    wrong_otp = "000000" if issued["otp"] != "000000" else "000001"

    for _ in range(5):
        response = api.client.post(
            "/api/auth/reset-password",
            json={
                "email": "priya@acme.com",
                "otp": wrong_otp,
                "newPassword": "Reset-password-2026",
            },
        )
        assert response.status_code == 400
    attempts = api.fake.execute(
        "SELECT attempts FROM password_reset_otps WHERE user_id = %s", (U["priya"],)
    )[0]["attempts"]
    assert attempts == 5


def test_mailpit_failure_is_visible_and_removes_unsent_otp(api, monkeypatch):
    from app.services import auth_service

    api.fake.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (hash_password("Initial-password-2026"), U["priya"]),
    )

    def fail_sending(_email, _otp):
        raise HTTPException(
            status_code=503, detail="Password reset email is temporarily unavailable."
        )

    monkeypatch.setattr(auth_service, "send_password_reset_otp", fail_sending)
    response = api.client.post("/api/auth/forgot-password", json={"email": "priya@acme.com"})
    assert response.status_code == 503
    assert "priya@acme.com" not in response.text
    assert not api.fake.execute(
        "SELECT user_id FROM password_reset_otps WHERE user_id = %s", (U["priya"],)
    )


def test_there_is_no_public_signup_endpoint(api):
    response = api.client.post("/api/auth/signup", json={})
    assert response.status_code == 404
