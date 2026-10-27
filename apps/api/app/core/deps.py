import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import ACCESS_TOKEN_COOKIE, decode_access_token
from app.models.enums import UserRole
from app.models.user import User

# auto_error=False — 쿠키로도 인증할 수 있으므로 헤더가 없다고 바로 401을 던지지 않는다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str | None = Depends(oauth2_scheme),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증 정보가 유효하지 않습니다",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token = bearer_token or request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        raise credentials_error
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        raise credentials_error
    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or not user.is_active or user.approval_status != "approved":
        raise credentials_error  # 승인 대기·거절·비활성 계정은 기존 토큰이 있어도 내부 자료에 접근할 수 없다
    return user


def require_roles(*roles: UserRole):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"이 작업은 {', '.join(r.value for r in roles)} 권한이 필요합니다",
            )
        return user

    return dependency


# ---- 외부 전문가(집필·검토) 접근 제한 ------------------------------------------
EXTERNAL_ROLES = (UserRole.AUTHOR, UserRole.EXT_REVIEWER)
EXTERNAL_ALLOWED_PREFIXES = ("/auth", "/journal/portal", "/docs", "/openapi.json", "/health")


def guard_external_users(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: str | None = Depends(oauth2_scheme),
) -> None:
    """외부 집필·검토 전문가 계정은 전용 포털(/journal/portal)과 인증 API 외의 모든 내부 API에 접근할 수 없다.

    개별 라우터가 역할을 따로 확인하지 않는 조회 API(후보주제·이슈·문서 등)까지 일괄 차단하기 위한 앱 전역 의존성이다.
    """
    token = bearer_token or request.cookies.get(ACCESS_TOKEN_COOKIE)
    if not token:
        return
    payload = decode_access_token(token)
    if payload is None or "sub" not in payload:
        return
    try:
        user = db.get(User, uuid.UUID(payload["sub"]))
    except ValueError:
        return
    if user is not None and user.role in EXTERNAL_ROLES and not request.url.path.startswith(EXTERNAL_ALLOWED_PREFIXES):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "외부 전문가 계정은 원고 포털만 사용할 수 있습니다")
