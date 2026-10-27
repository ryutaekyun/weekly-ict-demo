"""관리자 계정 관리 — 가입 승인·거절, 역할 변경, 비활성화, 초대 링크 발급. 모든 변경은 감사 로그에 남는다."""
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import require_roles
from app.models.enums import UserRole
from app.models.user import User
from app.models.user_invite import UserInvite

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(UserRole.ADMIN)

INTERNAL_ROLES = [UserRole.RESEARCHER, UserRole.REVIEWER, UserRole.APPROVER, UserRole.SOURCE_ADMIN, UserRole.ADMIN]


class AdminUserOut(BaseModel):
    id: str
    email: str
    display_name: str
    job_title: str | None
    role: str
    is_active: bool
    approval_status: str
    registered_via: str
    created_at: datetime
    last_login_at: datetime | None


def _out(u: User) -> AdminUserOut:
    return AdminUserOut(id=str(u.id), email=u.email, display_name=u.display_name, job_title=u.job_title, role=u.role.value, is_active=u.is_active,
                        approval_status=u.approval_status, registered_via=u.registered_via, created_at=u.created_at, last_login_at=u.last_login_at)


def _get(db: Session, user_id: uuid.UUID) -> User:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사용자를 찾을 수 없습니다")
    return u


def _active_admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.approval_status == "approved")) or 0


@router.get("/users", response_model=list[AdminUserOut])
def list_users(approval_status: str | None = None, db: Session = Depends(get_db), _: User = Depends(admin_only)):
    stmt = select(User).where(User.role.notin_([UserRole.AUTHOR, UserRole.EXT_REVIEWER]))  # 외부 전문가는 주간기술동향지 전용 화면에서 관리
    if approval_status:
        stmt = stmt.where(User.approval_status == approval_status)
    users = db.scalars(stmt.order_by(User.created_at.desc())).all()
    order = {"pending": 0, "approved": 1, "rejected": 2}
    return [_out(u) for u in sorted(users, key=lambda u: order.get(u.approval_status, 9))]


class ApproveBody(BaseModel):
    role: UserRole | None = None


@router.post("/users/{user_id}/approve", response_model=AdminUserOut)
def approve(user_id: uuid.UUID, body: ApproveBody | None = None, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    u = _get(db, user_id)
    if body and body.role is not None:
        if body.role not in INTERNAL_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="내부 업무 역할만 지정할 수 있습니다")
        u.role = body.role
    u.approval_status = "approved"
    u.approved_at = datetime.now(timezone.utc)
    log_action(db, actor_user_id=admin.id, action="user.approve", entity_type="user", entity_id=u.id, detail={"role": u.role.value})
    db.commit()
    return _out(u)


@router.post("/users/{user_id}/reject", response_model=AdminUserOut)
def reject(user_id: uuid.UUID, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    u = _get(db, user_id)
    if u.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="본인 계정은 거절할 수 없습니다")
    u.approval_status = "rejected"
    log_action(db, actor_user_id=admin.id, action="user.reject", entity_type="user", entity_id=u.id)
    db.commit()
    return _out(u)


class UserPatch(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def patch_user(user_id: uuid.UUID, body: UserPatch, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    u = _get(db, user_id)
    losing_admin = (body.role is not None and body.role != UserRole.ADMIN and u.role == UserRole.ADMIN) or (body.is_active is False and u.role == UserRole.ADMIN)
    if losing_admin and _active_admin_count(db) <= 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="마지막 관리자 계정은 역할 변경·비활성화할 수 없습니다")
    if body.is_active is False and u.id == admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="본인 계정은 비활성화할 수 없습니다")
    detail = {}
    if body.role is not None:
        if body.role not in INTERNAL_ROLES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="내부 업무 역할만 지정할 수 있습니다")
        detail["role"] = [u.role.value, body.role.value]
        u.role = body.role
    if body.is_active is not None:
        detail["is_active"] = [u.is_active, body.is_active]
        u.is_active = body.is_active
    log_action(db, actor_user_id=admin.id, action="user.update", entity_type="user", entity_id=u.id, detail=detail)
    db.commit()
    return _out(u)


class InviteCreate(BaseModel):
    email: EmailStr
    role: UserRole = UserRole.RESEARCHER
    valid_days: int = Field(default=7, ge=1, le=30)


class InviteOut(BaseModel):
    id: str
    email: str
    role: str
    expires_at: datetime
    used: bool


@router.post("/invites")
def create_invite(body: InviteCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """초대 링크 발급 — 토큰 원문은 이 응답에서만 보여 주며 DB에는 해시만 저장한다. 메일은 자동 발송하지 않으므로 관리자가 직접 전달한다."""
    if body.role not in INTERNAL_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="내부 업무 역할만 초대할 수 있습니다")
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다")
    token = secrets.token_urlsafe(32)
    inv = UserInvite(email=email, role=body.role, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     expires_at=datetime.now(timezone.utc) + timedelta(days=body.valid_days), created_by_user_id=admin.id)
    db.add(inv)
    db.flush()
    log_action(db, actor_user_id=admin.id, action="user.invite", entity_type="user_invite", entity_id=inv.id, detail={"email": email, "role": body.role.value})
    db.commit()
    return {"id": str(inv.id), "email": email, "role": body.role.value, "expires_at": inv.expires_at.isoformat(),
            "register_path": f"/register?invite={token}", "note": "이 링크는 지금만 표시됩니다. 초대받은 이메일 주소로만 가입할 수 있습니다."}


@router.get("/invites", response_model=list[InviteOut])
def list_invites(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    rows = db.scalars(select(UserInvite).order_by(UserInvite.created_at.desc()).limit(100)).all()
    return [InviteOut(id=str(i.id), email=i.email, role=i.role.value, expires_at=i.expires_at, used=i.used_at is not None) for i in rows]
