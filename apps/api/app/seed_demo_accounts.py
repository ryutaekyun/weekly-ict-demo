"""시연용 가상 계정(연구원·승인권자·관리자) 3개를 새로 만든다. 비밀번호는 실행할 때 무작위로 만들어 로컬 파일에만 저장한다.

- 저장소에 비밀번호를 하드코딩하지 않는다. 결과 파일 apps/api/demo_accounts.local.txt 는 .gitignore 대상이라 공개 저장소에 올라가지 않는다.
- 이미 같은 이메일이 있으면 건드리지 않는다(기존 계정·비밀번호는 변경하지 않음). 전부 example.com(IANA 예약 도메인)의 가상 인물이다.
실행: python -m app.seed_demo_accounts
"""

import secrets
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User

ACCOUNTS = [
    ("demo-researcher@example.com", "시연 연구원", UserRole.RESEARCHER),
    ("demo-approver@example.com", "시연 승인권자", UserRole.APPROVER),
    ("demo-admin@example.com", "시연 관리자", UserRole.ADMIN),
]


def main() -> None:
    db = SessionLocal()
    lines, skipped = [], []
    try:
        for email, name, role in ACCOUNTS:
            if db.scalar(select(User).where(User.email == email)) is not None:
                skipped.append(email)
                continue
            pw = secrets.token_urlsafe(12)
            db.add(User(email=email, password_hash=hash_password(pw), display_name=name, role=role))
            lines.append(f"{email} / {pw} / {role.value}")
        db.commit()
    finally:
        db.close()
    if lines:
        out = Path("demo_accounts.local.txt")
        out.write_text("# 시연용 가상 계정(로컬 전용 - 공개 저장소에 올리지 마세요)\n" + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"가상 계정 {len(lines)}개를 만들고 비밀번호를 {out.resolve()} 에 저장했습니다.")
    if skipped:
        print("이미 있는 계정(변경하지 않음): " + ", ".join(skipped) + " — 비밀번호를 잃어버렸다면 이 파일을 지우고 다른 이메일로 다시 만들거나 DB를 새로 시드하세요.")


if __name__ == "__main__":
    main()
