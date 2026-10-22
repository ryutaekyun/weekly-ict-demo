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
    if user is None or not user.is_active:
        raise credentials_error
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
