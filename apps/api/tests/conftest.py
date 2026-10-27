import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

# 기본은 SQLite 인메모리(빠른 로컬 실행). CI에서 TEST_DATABASE_URL을 실제 PostgreSQL로
# 지정하면 동일한 테스트 스위트가 PostgreSQL에서도 통과하는지 그대로 검증할 수 있다
# (Phase 2-4 지시사항 — "기존 SQLite 테스트가 PostgreSQL에서도 동작하는지 검증").
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
_is_sqlite = TEST_DATABASE_URL.startswith("sqlite")


@pytest.fixture()
def db_session():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False} if _is_sqlite else {},
        poolclass=StaticPool if _is_sqlite else None,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)  # PostgreSQL은 테스트 간 상태가 남으므로 매번 깨끗하게 시작한다
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(db_session, email: str, role: UserRole, display_name: str = "테스트사용자") -> User:
    user = User(
        email=email,
        password_hash=hash_password("TestPass!123"),
        display_name=display_name,
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def auth_headers(client: TestClient, email: str) -> dict:
    resp = client.post("/auth/login", json={"email": email, "password": "TestPass!123"})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _ai_approval_off_by_default(monkeypatch):
    """기존 AI 테스트는 모의/가짜 공급자로 승인 게이트 없이 돌린다 — 게이트 자체는 test_ai_phase362.py가 AI_REQUIRE_APPROVAL=1로 따로 검증한다."""
    monkeypatch.setenv("AI_REQUIRE_APPROVAL", "0")
