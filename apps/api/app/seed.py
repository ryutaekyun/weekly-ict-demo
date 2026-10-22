"""개발용 초기 사용자 시드 스크립트.

실행: python -m app.seed
실제 제안서 인력투입계획표(docs/PLATFORM_PLAN.md 참고)의 11명 역할을 반영한다.
비밀번호는 전부 임시값이며 최초 로그인 후 반드시 변경해야 한다 — 운영 배포 전 교체 필수.
"""

from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User

SEED_USERS = [
    ("heo.seonyang@tenopa.co.kr", "허선양", UserRole.ADMIN, "수석연구원"),
    ("ha.miham@tenopa.co.kr", "하미함", UserRole.APPROVER, "책임연구원"),
    ("lee.donghyuk@tenopa.co.kr", "이동혁", UserRole.REVIEWER, "책임연구원"),
    ("ryu.taekyun@tenopa.co.kr", "류태균", UserRole.REVIEWER, "책임연구원"),
    ("park.seonjeong@tenopa.co.kr", "박선정", UserRole.REVIEWER, "선임연구원"),
    ("noh.uijeong@tenopa.co.kr", "노의정", UserRole.RESEARCHER, "전임연구원"),
    ("lee.jeongcheol@tenopa.co.kr", "이정철", UserRole.RESEARCHER, "전임연구원"),
    ("kim.dabi@tenopa.co.kr", "김다비", UserRole.RESEARCHER, "전임연구원"),
    ("park.hayoon@tenopa.co.kr", "박하윤", UserRole.RESEARCHER, "전임연구원"),
    ("lee.jeongmin@tenopa.co.kr", "이정민", UserRole.RESEARCHER, "전임연구원"),
    ("jeon.seyoung@tenopa.co.kr", "전세영", UserRole.RESEARCHER, "전임연구원"),
]

DEFAULT_PASSWORD = "ChangeMe!2026"


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for email, name, role, job_title in SEED_USERS:
            exists = db.query(User).filter(User.email == email).first()
            if exists:
                continue
            db.add(
                User(
                    email=email,
                    password_hash=hash_password(DEFAULT_PASSWORD),
                    display_name=name,
                    role=role,
                    job_title=job_title,
                )
            )
        db.commit()
        print(f"시드 완료 — 임시 비밀번호: {DEFAULT_PASSWORD} (최초 로그인 후 반드시 변경할 것)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
