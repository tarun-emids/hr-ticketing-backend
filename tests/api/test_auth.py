from app.services.passwords import verify_password


def test_forgot_password_returns_generic_message_for_unknown_email(api, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.auth_service.send_password_reset_email",
        lambda recipient, code: sent.append((recipient, code)),
    )

    response = api.client.post(
        "/api/auth/forgot-password",
        json={"email": "not-found@acme.com"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "message": "If an account exists for this address, a reset code has been emailed."
    }
    assert sent == []


def test_forgot_password_reset_code_changes_password_and_is_single_use(api, monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.services.auth_service.send_password_reset_email",
        lambda recipient, code: sent.append((recipient, code)),
    )

    requested = api.client.post(
        "/api/auth/forgot-password",
        json={"email": "PRIYA@acme.com"},
    )

    assert requested.status_code == 200
    assert requested.json()["message"].startswith("If an account exists")
    assert len(sent) == 1
    recipient, code = sent[0]
    assert recipient == "priya@acme.com"
    assert len(code) == 6 and code.isdigit()

    reset = api.client.post(
        "/api/auth/reset-password",
        json={
            "email": "priya@acme.com",
            "otp": code,
            "newPassword": "a-new-password-123",
        },
    )

    assert reset.status_code == 200
    assert "successfully" in reset.json()["message"]
    row = api.fake.execute(
        "SELECT password_hash FROM users WHERE lower(email) = lower(?)",
        ("priya@acme.com",),
    )[0]
    assert verify_password("a-new-password-123", row["password_hash"])

    reused = api.client.post(
        "/api/auth/reset-password",
        json={
            "email": "priya@acme.com",
            "otp": code,
            "newPassword": "another-new-password",
        },
    )
    assert reused.status_code == 400
    assert reused.json()["detail"] == "Invalid or expired reset code."


def test_reset_password_rejects_invalid_code(api, monkeypatch):
    monkeypatch.setattr(
        "app.services.auth_service.send_password_reset_email",
        lambda _recipient, _code: None,
    )
    api.client.post("/api/auth/forgot-password", json={"email": "priya@acme.com"})

    response = api.client.post(
        "/api/auth/reset-password",
        json={
            "email": "priya@acme.com",
            "otp": "000000",
            "newPassword": "a-new-password-123",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid or expired reset code."
