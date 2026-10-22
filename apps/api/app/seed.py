"""로컬 개발·테스트 전용 더미 사용자 시드 스크립트.

실행: python -m app.seed

중요(보안): 여기 등록되는 계정은 전부 가상의 인물·이메일이며 실제 참여 연구원과
아무 관련이 없다. 비밀번호는 매 실행마다 새로 무작위 생성되어 콘솔에 한 번만
출력되고 코드 어디에도 저장되지 않는다.

운영 환경 계정은 이 스크립트로 만들지 않는다 — `python -m app.create_admin`으로
관리자가 직접, 1회성 비밀번호를 받아 생성한다(README 참고).
"""

import secrets

from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User

# (이메일, 표시 이름, 역할, 직함) — 전부 가상의 더미 데이터. example.com은 IANA가
# 문서/예시 용도로 예약한 도메인이라 실제 수신자가 존재할 수 없다.
DUMMY_USERS = [
    ("dev-admin@example.com", "더미 관리자", UserRole.ADMIN, "플랫폼 관리자"),
    ("dev-approver@example.com", "더미 승인자", UserRole.APPROVER, "최종 승인 테스트 계정"),
    ("dev-reviewer-1@example.com", "더미 검토자1", UserRole.REVIEWER, "검토 테스트 계정"),
    ("dev-reviewer-2@example.com", "더미 검토자2", UserRole.REVIEWER, "검토 테스트 계정"),
    ("dev-reviewer-3@example.com", "더미 검토자3", UserRole.REVIEWER, "검토 테스트 계정"),
    ("dev-researcher-1@example.com", "더미 연구원1", UserRole.RESEARCHER, "연구원 테스트 계정"),
    ("dev-researcher-2@example.com", "더미 연구원2", UserRole.RESEARCHER, "연구원 테스트 계정"),
    ("dev-researcher-3@example.com", "더미 연구원3", UserRole.RESEARCHER, "연구원 테스트 계정"),
    ("dev-researcher-4@example.com", "더미 연구원4", UserRole.RESEARCHER, "연구원 테스트 계정"),
    ("dev-researcher-5@example.com", "더미 연구원5", UserRole.RESEARCHER, "연구원 테스트 계정"),
    ("dev-researcher-6@example.com", "더미 연구원6", UserRole.RESEARCHER, "연구원 테스트 계정"),
]


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = []
        for email, name, role, job_title in DUMMY_USERS:
            if db.query(User).filter(User.email == email).first():
                continue
            password = secrets.token_urlsafe(12)
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(password),
                    display_name=name,
                    role=role,
                    job_title=job_title,
                )
            )
            created.append((email, password))
        db.commit()

        if not created:
            print("이미 모든 더미 계정이 존재합니다 — 새로 만든 계정이 없습니다.")
            return

        print("더미 개발 계정이 생성되었습니다. 비밀번호는 이번 실행에서만 출력되며 저장되지 않습니다:")
        for email, password in created:
            print(f"  {email}  /  {password}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
