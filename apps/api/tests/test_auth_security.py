from app.core.security import ACCESS_TOKEN_COOKIE, CSRF_COOKIE
from app.models.enums import UserRole
from tests.conftest import auth_headers, make_user


def test_login_sets_httponly_access_cookie_and_readable_csrf_cookie(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    resp = client.post("/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"})
    assert resp.status_code == 200

    set_cookie_headers = resp.headers.get_list("set-cookie")
    access_cookie_header = next(h for h in set_cookie_headers if h.startswith(f"{ACCESS_TOKEN_COOKIE}="))
    csrf_cookie_header = next(h for h in set_cookie_headers if h.startswith(f"{CSRF_COOKIE}="))

    assert "httponly" in access_cookie_header.lower()
    assert "httponly" not in csrf_cookie_header.lower()  # 프런트 JS가 읽어서 헤더로 돌려보내야 함


def test_cookie_only_request_without_csrf_header_is_rejected(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    login_resp = client.post(
        "/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"}
    )
    assert login_resp.status_code == 200
    # client는 쿠키를 자동으로 보관하므로, Authorization 헤더 없이 쿠키만으로 다음 요청을 보낸다.
    resp = client.post("/candidates", json={"field_code": "ai", "title": "쿠키 전용 요청"})
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["detail"]


def test_cookie_request_with_matching_csrf_header_succeeds(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    client.post("/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"})
    csrf_token = client.cookies.get(CSRF_COOKIE)
    assert csrf_token

    resp = client.post(
        "/candidates",
        json={"field_code": "ai", "title": "CSRF 토큰 포함 요청"},
        headers={"x-csrf-token": csrf_token},
    )
    assert resp.status_code == 201, resp.text


def test_bearer_header_requests_are_exempt_from_csrf_check(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")
    resp = client.post("/candidates", json={"field_code": "ai", "title": "Bearer 요청"}, headers=headers)
    assert resp.status_code == 201


def test_account_locks_after_repeated_failed_logins(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    for _ in range(5):
        resp = client.post(
            "/auth/login", json={"email": "researcher@example.com", "password": "wrong-password"}
        )
        assert resp.status_code == 401

    # 6번째는 비밀번호가 맞아도 잠금 때문에 거부되어야 한다
    resp = client.post(
        "/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"}
    )
    assert resp.status_code == 429


def test_change_password_requires_correct_current_password(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    headers = auth_headers(client, "researcher@example.com")

    resp = client.patch(
        "/auth/password",
        json={"current_password": "wrong", "new_password": "NewPassword!123"},
        headers=headers,
    )
    assert resp.status_code == 401

    resp = client.patch(
        "/auth/password",
        json={"current_password": "TestPass!123", "new_password": "NewPassword!123"},
        headers=headers,
    )
    assert resp.status_code == 200

    # 이전 비밀번호로는 더 이상 로그인할 수 없고 새 비밀번호로는 가능해야 한다
    old_login = client.post(
        "/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"}
    )
    assert old_login.status_code == 401
    new_login = client.post(
        "/auth/login", json={"email": "researcher@example.com", "password": "NewPassword!123"}
    )
    assert new_login.status_code == 200


def test_logout_clears_cookies(client, db_session):
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    client.post("/auth/login", json={"email": "researcher@example.com", "password": "TestPass!123"})
    assert client.cookies.get(ACCESS_TOKEN_COOKIE)

    client.post("/auth/logout")
    assert client.cookies.get(ACCESS_TOKEN_COOKIE) is None
