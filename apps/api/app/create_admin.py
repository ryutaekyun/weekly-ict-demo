"""운영 환경에서 최초 관리자 계정을 안전하게 만드는 스크립트.

이메일은 인자로 받고, 비밀번호는 절대 커맨드라인 인자나 코드에 두지 않는다 — 터미널에서
숨김 입력(getpass)으로 직접 받거나, 지정하지 않으면 강력한 임의 비밀번호를 생성해 1회만
화면에 보여준다.

사용 예:
    python -m app.create_admin --email admin@tenopa.co.kr --name "홍길동"
    python -m app.create_admin --email admin@tenopa.co.kr --name "홍길동" --prompt-password
"""

import argparse
import getpass
import secrets
import sys

from sqlalchemy import select

from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


def main() -> None:
    parser = argparse.ArgumentParser(description="최초 관리자 계정 생성")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, help="표시 이름")
    parser.add_argument("--job-title", default="플랫폼 관리자")
    parser.add_argument(
        "--prompt-password",
        action="store_true",
        help="지정 시 터미널에서 비밀번호를 직접 입력받는다(미지정 시 임의 생성)",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.scalar(select(User).where(User.email == args.email))
        if existing is not None:
            print(f"이미 존재하는 이메일입니다: {args.email}", file=sys.stderr)
            sys.exit(1)

        if args.prompt_password:
            password = getpass.getpass("새 관리자 비밀번호 입력(입력값은 화면에 표시되지 않음): ")
            confirm = getpass.getpass("비밀번호 확인: ")
            if password != confirm:
                print("비밀번호가 일치하지 않습니다.", file=sys.stderr)
                sys.exit(1)
        else:
            password = secrets.token_urlsafe(16)

        user = User(
            email=args.email,
            password_hash=hash_password(password),
            display_name=args.name,
            role=UserRole.ADMIN,
            job_title=args.job_title,
        )
        db.add(user)
        db.commit()

        print(f"관리자 계정 생성 완료: {args.email}")
        if not args.prompt_password:
            print(f"임시 비밀번호(한 번만 출력됨, 기록 후 즉시 로그인해 변경할 것): {password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
