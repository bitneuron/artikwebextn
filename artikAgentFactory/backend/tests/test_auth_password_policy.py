from app.core.password_policy import validate_password


def test_rejects_short_password():
    assert validate_password("short1") != []


def test_rejects_common_password():
    assert validate_password("password123") != []


def test_rejects_password_containing_email_local_part():
    problems = validate_password("janedoe-something-99", email="janedoe@example.com")
    assert any("email" in p.lower() for p in problems)


def test_rejects_password_containing_username():
    problems = validate_password("mycoolusername-99", username="mycoolusername")
    assert any("username" in p.lower() for p in problems)


def test_accepts_strong_unrelated_password():
    assert validate_password("correct-horse-battery-staple-42", email="a@b.com", username="someone") == []


def test_via_api_weak_password_rejected_on_change(client):
    from tests.conftest import ADMIN_PASSWORD, login_as

    login_as(client, "administrator")
    resp = client.post("/api/auth/change-password", json={
        "current_password": ADMIN_PASSWORD, "new_password": "short",
    })
    assert resp.status_code == 422
