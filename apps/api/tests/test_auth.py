from app.models.enums import UserRole
from tests.conftest import auth_headers, make_user


def test_login_success(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    resp = client.post(
        "/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    resp = client.post(
        "/auth/login", json={"email": "researcher@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_login_unknown_email(client):
    resp = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_returns_current_user(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER, "홍길동")
    headers = auth_headers(client, "researcher@example.com")
    resp = client.get("/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "researcher@example.com"
    assert body["display_name"] == "홍길동"
    assert body["role"] == "researcher"
