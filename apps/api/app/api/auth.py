from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.security import (
    ACCESS_TOKEN_COOKIE,
    CSRF_COOKIE,
    create_access_token,
    generate_csrf_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, PasswordChangeRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "이메일 또는 비밀번호가 올바르지 않습니다"


def _set_auth_cookies(response: Response, token: str) -> None:
    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    # CSRF 쿠키는 프런트엔드 JS가 읽어서 요청 헤더로 되돌려보내야 하므로 httponly를 걸지 않는다.
    response.set_cookie(
        CSRF_COOKIE,
        generate_csrf_token(),
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email))

    if user is not None and user.locked_until is not None:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            # SQLite는 timezone-aware 컬럼이어도 naive datetime으로 돌려주므로 UTC로 간주해 보정한다
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"로그인 시도가 너무 많습니다. {settings.login_lockout_minutes}분 후 다시 시도하세요",
            )
        # 잠금 시간이 지났으면 카운터를 초기화하고 계속 진행
        user.failed_login_attempts = 0
        user.locked_until = None

    # 사용자 존재 여부를 노출하지 않기 위해 항상 동일한 오류 메시지를 사용한다
    if user is None or not verify_password(payload.password, user.password_hash):
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.max_failed_login_attempts:
                user.locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.login_lockout_minutes
                )
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다")

    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    token = create_access_token(subject=str(user.id), role=user.role.value)
    _set_auth_cookies(response, token)
    # 토큰을 응답 본문에도 담아 비브라우저 클라이언트(테스트, 외부 연동)는 Authorization
    # 헤더 방식도 계속 쓸 수 있게 한다. 브라우저 프런트엔드는 이 값을 저장하지 않고
    # httpOnly 쿠키에만 의존한다.
    return TokenResponse(access_token=token)


@router.post("/logout")
def logout(response: Response):
    # set_cookie 때와 동일한 속성(path/secure/samesite)으로 지워야 브라우저가 같은 쿠키로 인식해 삭제한다
    response.delete_cookie(ACCESS_TOKEN_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=settings.cookie_secure, samesite="lax")
    return {"detail": "로그아웃되었습니다"}


@router.get("/me", response_model=UserOut)
def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/password")
def change_password(
    payload: PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="현재 비밀번호가 올바르지 않습니다")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="새 비밀번호가 기존 비밀번호와 같습니다")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"detail": "비밀번호가 변경되었습니다"}
