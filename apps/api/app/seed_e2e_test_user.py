"""Playwright 브라우저 E2E 테스트 전용 계정 시드 스크립트.

`app.seed`는 보안을 위해 매 실행마다 무작위 비밀번호를 생성해 1회만 출력하지만,
자동화된 E2E 테스트는 고정된 비밀번호가 필요하다. 그래서 이 스크립트는 별도로
"e2e-" 접두사가 붙은 가상 계정만 고정 비밀번호로 생성/갱신한다.

로컬 개발·CI 테스트 전용이며 운영 환경에서는 절대 실행하지 않는다.
실행: python -m app.seed_e2e_test_user
"""

from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User

E2E_ADMIN_EMAIL = "e2e-admin@example.com"
E2E_ADMIN_PASSWORD = "E2eTest-Fixed-Pw-Admin-001!"
E2E_RESEARCHER_EMAIL = "e2e-researcher@example.com"
E2E_RESEARCHER_PASSWORD = "E2eTest-Fixed-Pw-Researcher-002!"

ACCOUNTS = [
    (E2E_ADMIN_EMAIL, E2E_ADMIN_PASSWORD, "E2E 테스트 관리자", UserRole.ADMIN),
    (E2E_RESEARCHER_EMAIL, E2E_RESEARCHER_PASSWORD, "E2E 테스트 연구원", UserRole.RESEARCHER),
]


def seed_e2e_test_users() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for email, password, name, role in ACCOUNTS:
            user = db.query(User).filter(User.email == email).one_or_none()
            if user is None:
                db.add(User(email=email, password_hash=hash_password(password), display_name=name, role=role))
            else:
                user.password_hash = hash_password(password)
                user.failed_login_attempts = 0
                user.locked_until = None
        db.commit()
        print("E2E 테스트 계정이 고정 비밀번호로 준비되었습니다(운영 환경에서 실행 금지).")
    finally:
        db.close()


if __name__ == "__main__":
    seed_e2e_test_users()
