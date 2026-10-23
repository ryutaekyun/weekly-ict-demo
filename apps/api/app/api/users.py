from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.enums import UserRole
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


class UserSummaryOut(BaseModel):
    id: str
    display_name: str
    role: str
    email: str


@router.get("", response_model=list[UserSummaryOut])
def list_users(
    role: UserRole | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """검토자·담당자 지정 드롭다운용 — 비밀번호 등 민감정보는 포함하지 않는다."""
    stmt = select(User).where(User.is_active.is_(True))
    if role is not None:
        stmt = stmt.where(User.role == role)
    users = db.scalars(stmt.order_by(User.display_name)).all()
    return [UserSummaryOut(id=str(u.id), display_name=u.display_name, role=u.role.value, email=u.email) for u in users]
