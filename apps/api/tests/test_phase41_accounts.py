"""Phase 4-1 — 회원가입·관리자 승인·초대·내 정보·계정 비활성화."""
from app.models.enums import UserRole
from tests.conftest import auth_headers, make_user

PW = "Researcher#2026a"


def _register(client, email="a@example.com", **kw):
    body = {"email": email, "display_name": "연구원 A", "password": PW, **kw}
    return client.post("/auth/register", json=body)


def test_register_is_pending_and_cannot_login_until_approved(client, db_session):
    admin = make_user(db_session, "adm@example.com", UserRole.ADMIN)
    r = _register(client)
    assert r.status_code == 201 and r.json()["status"] == "pending"
    # 잘못된 비밀번호는 상태를 알려 주지 않는다
    assert client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-password-1"}).status_code == 401
    r = client.post("/auth/login", json={"email": "a@example.com", "password": PW})
    assert r.status_code == 403 and "승인 대기" in r.json()["detail"]
    h = auth_headers(client, "adm@example.com")
    pending = client.get("/admin/users?approval_status=pending", headers=h).json()
    assert [u["email"] for u in pending] == ["a@example.com"]
    ok = client.post(f"/admin/users/{pending[0]['id']}/approve", json={"role": "reviewer"}, headers=h)
    assert ok.status_code == 200 and ok.json()["role"] == "reviewer"
    login = client.post("/auth/login", json={"email": "a@example.com", "password": PW})
    assert login.status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
    assert me["approval_status"] == "approved" and me["role"] == "reviewer"
    assert admin.id  # 관리자 계정 유지


def test_rejected_and_duplicate_and_weak_password(client, db_session):
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    assert _register(client, "b@example.com").status_code == 201
    assert _register(client, "b@example.com").status_code == 409
    assert _register(client, "c@example.com", password="onlyletterspassword").status_code == 422  # 숫자 없음
    assert _register(client, "c@example.com", password="Short1").status_code == 422
    h = auth_headers(client, "adm@example.com")
    uid = client.get("/admin/users?approval_status=pending", headers=h).json()[0]["id"]
    assert client.post(f"/admin/users/{uid}/reject", headers=h).status_code == 200
    r = client.post("/auth/login", json={"email": "b@example.com", "password": PW})
    assert r.status_code == 403 and "승인되지" in r.json()["detail"]


def test_pending_token_cannot_reach_internal_data(client, db_session):
    """승인 전에는 토큰이 있어도(예: 승인 후 거절된 경우) 내부 자료에 접근할 수 없다."""
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    u = make_user(db_session, "r1@example.com", UserRole.RESEARCHER)
    h = auth_headers(client, "r1@example.com")
    assert client.get("/candidates", headers=h).status_code == 200
    u.approval_status = "pending"
    db_session.commit()
    assert client.get("/candidates", headers=h).status_code == 401
    assert client.get("/auth/me", headers=h).status_code == 401


def test_only_admin_manages_accounts(client, db_session):
    make_user(db_session, "r1@example.com", UserRole.RESEARCHER)
    h = auth_headers(client, "r1@example.com")
    assert client.get("/admin/users", headers=h).status_code == 403
    assert client.post("/admin/invites", json={"email": "x@example.com"}, headers=h).status_code == 403


def test_invite_registers_approved_with_role_and_is_single_use(client, db_session):
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    h = auth_headers(client, "adm@example.com")
    inv = client.post("/admin/invites", json={"email": "Inv@Example.com", "role": "source_admin"}, headers=h)
    assert inv.status_code == 200
    token = inv.json()["register_path"].split("invite=")[1]
    assert "token" not in client.get("/admin/invites", headers=h).text  # 토큰 원문은 목록에 없다
    wrong = _register(client, "other@example.com", invite_token=token)
    assert wrong.status_code == 400  # 초대받은 이메일이 아니면 불가
    ok = _register(client, "inv@example.com", invite_token=token)
    assert ok.status_code == 201 and ok.json()["status"] == "approved"
    login = client.post("/auth/login", json={"email": "inv@example.com", "password": PW})
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).json()
    assert me["role"] == "source_admin"
    assert _register(client, "inv2@example.com", invite_token=token).status_code == 400  # 재사용 불가


def test_profile_favorites_and_deactivate_last_admin_guard(client, db_session):
    adm = make_user(db_session, "adm@example.com", UserRole.ADMIN)
    make_user(db_session, "r1@example.com", UserRole.RESEARCHER)
    rh = auth_headers(client, "r1@example.com")
    r = client.patch("/auth/me", json={"display_name": "새 이름", "favorite_fields": ["ai", "sec"]}, headers=rh)
    assert r.status_code == 200 and r.json()["favorite_fields"] == ["ai", "sec"] and r.json()["role"] == "researcher"
    assert client.patch("/auth/me", json={"favorite_fields": ["nope"]}, headers=rh).status_code == 400
    h = auth_headers(client, "adm@example.com")
    assert client.patch(f"/admin/users/{adm.id}", json={"is_active": False}, headers=h).status_code == 400  # 마지막 관리자·본인
    uid = [u for u in client.get("/admin/users", headers=h).json() if u["email"] == "r1@example.com"][0]["id"]
    assert client.patch(f"/admin/users/{uid}", json={"is_active": False}, headers=h).status_code == 200
    assert client.post("/auth/login", json={"email": "r1@example.com", "password": "TestPass!123"}).status_code == 403


def test_work_dashboard_returns_personal_sections(client, db_session):
    make_user(db_session, "r1@example.com", UserRole.RESEARCHER)
    h = auth_headers(client, "r1@example.com")
    client.patch("/auth/me", json={"favorite_fields": ["ai"]}, headers=h)
    r = client.get("/dashboard/work", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert set(body["kpi"]) == {"new_today", "total_docs", "pending_candidates", "my_manuscripts", "source_errors"}
    assert body["favorite_fields"] == ["ai"]
    for k in ("recent_docs", "favorite_docs", "issues", "priority", "my_tasks", "review_requests", "history"):
        assert isinstance(body[k], list)
    client.cookies.clear()
    assert client.get("/dashboard/work").status_code == 401


def test_production_refuses_unsafe_settings():
    import pytest
    from pydantic import ValidationError
    from app.core.config import Settings
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="change-me-in-env", cookie_secure=True)
    with pytest.raises(ValidationError):
        Settings(app_env="production", jwt_secret="x" * 40, cookie_secure=False)
    Settings(app_env="production", jwt_secret="x" * 40, cookie_secure=True)  # 안전한 설정은 통과


def test_register_rate_limit_per_ip(client, db_session):
    from app.core import ratelimit
    ratelimit.reset()
    codes = [_register(client, f"rl{i}@example.com").status_code for i in range(22)]
    assert codes[:20] == [201] * 20 and codes[20:] == [429, 429]
    ratelimit.reset()
