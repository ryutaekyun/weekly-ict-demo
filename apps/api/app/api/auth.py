from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
import hashlib
import json

from app.core import ratelimit
from app.core.audit import log_action
from app.models.enums import FieldCode, UserRole
from app.models.user_invite import UserInvite
from app.schemas.auth import LoginRequest, PasswordChangeRequest, ProfileUpdate, RegisterRequest, RegisterResponse, TokenResponse, UserOut

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


def _user_out(u: User) -> UserOut:
    try:
        favs = json.loads(u.favorite_fields_json) if u.favorite_fields_json else []
    except ValueError:
        favs = []
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, role=u.role, job_title=u.job_title, is_active=u.is_active,
                   approval_status=u.approval_status, favorite_fields=[f for f in favs if isinstance(f, str)], last_login_at=u.last_login_at)


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """연구원 회원가입 — 기본은 관리자 승인 대기(pending). 관리자가 발급한 초대 링크로 가입하면 초대된 역할로 바로 승인된다.
    이메일 소유 확인 메일은 SMTP가 연결되기 전까지 보내지 않으며, 그 대신 관리자 승인·초대 방식을 쓴다."""
    ip = request.client.host if request.client else "unknown"
    if not ratelimit.allow(f"register:{ip}", limit=20, window_seconds=600):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="가입 신청이 너무 많습니다. 잠시 후 다시 시도하세요")
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다")
    role, approval, via, invite = UserRole.RESEARCHER, "pending", "self", None
    if payload.invite_token:
        digest = hashlib.sha256(payload.invite_token.encode()).hexdigest()
        invite = db.scalar(select(UserInvite).where(UserInvite.token_hash == digest))
        exp = None
        if invite is not None:
            exp = invite.expires_at.replace(tzinfo=timezone.utc) if invite.expires_at.tzinfo is None else invite.expires_at
        if invite is None or invite.used_at is not None or exp < datetime.now(timezone.utc) or invite.email.lower() != email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="초대 링크가 올바르지 않거나 만료되었습니다")
        role, approval, via = invite.role, "approved", "invite"
    user = User(email=email, password_hash=hash_password(payload.password), display_name=payload.display_name.strip(), role=role,
                job_title=payload.job_title, is_active=True, approval_status=approval, registered_via=via,
                approved_at=datetime.now(timezone.utc) if approval == "approved" else None)
    db.add(user)
    db.flush()
    if invite is not None:
        invite.used_at = datetime.now(timezone.utc)
    log_action(db, actor_user_id=user.id, action="user.register", entity_type="user", entity_id=user.id, detail={"via": via, "approval": approval})
    db.commit()
    msg = "가입이 완료되었습니다. 바로 로그인할 수 있습니다." if approval == "approved" else "가입 신청이 접수되었습니다. 관리자 승인 후 로그인할 수 있습니다."
    return RegisterResponse(status=approval, message=msg)


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

    # 비밀번호가 맞은 뒤에만 계정 상태를 알려 준다(계정 존재 여부 노출 방지)
    if user.approval_status == "pending":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 승인 대기 중입니다. 승인 후 로그인할 수 있습니다")
    if user.approval_status == "rejected":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="가입이 승인되지 않았습니다. 관리자에게 문의하세요")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다")

    user.last_login_at = datetime.now(timezone.utc)
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
    return _user_out(current_user)


@router.patch("/me", response_model=UserOut)
def update_me(payload: ProfileUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """내 정보(이름·직함·관심 ICT 분야) 수정 — 역할·승인 상태는 여기서 바꿀 수 없다."""
    if payload.display_name is not None:
        current_user.display_name = payload.display_name.strip()
    if payload.job_title is not None:
        current_user.job_title = payload.job_title.strip() or None
    if payload.favorite_fields is not None:
        valid = {f.value for f in FieldCode}
        bad = [f for f in payload.favorite_fields if f not in valid]
        if bad:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"알 수 없는 분야 코드: {', '.join(bad)}")
        current_user.favorite_fields_json = json.dumps(sorted(set(payload.favorite_fields)), ensure_ascii=False)
    log_action(db, actor_user_id=current_user.id, action="user.profile.update", entity_type="user", entity_id=current_user.id)
    db.commit()
    return _user_out(current_user)


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
