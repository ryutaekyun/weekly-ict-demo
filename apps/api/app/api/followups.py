import json
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.card_news import CardNews
from app.models.enums import UserRole
from app.models.followup import FollowupAck, FollowupNotice
from app.models.manuscript import Manuscript
from app.models.report import Report
from app.models.user import User
from app.services import followup_service as svc

router = APIRouter(prefix="/followups", tags=["followups"])
PRIVILEGED = (UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)


class Change(BaseModel):
    item: str = Field(min_length=1, max_length=200)
    old: str = Field(max_length=300)
    new: str = Field(max_length=300)


class NoticeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    original_doc_number: str = Field(min_length=3, max_length=100)
    original_url: str | None = None
    followup_doc_number: str | None = None
    followup_url: str = Field(min_length=8, max_length=1000)
    followup_org: str | None = None
    followup_published_at: datetime | None = None
    followup_effective_on: str | None = None
    change_summary: str = Field(min_length=1)
    changes: list[Change] = []
    is_pilot: bool = False


class AckBody(BaseModel):
    entity_type: Literal["manuscript", "report", "card_news"]
    entity_id: uuid.UUID
    resolution: Literal["updated", "no_change"]
    note: str = Field(min_length=3)


def _entity(db: Session, etype: str, eid: uuid.UUID):
    model = {"manuscript": Manuscript, "report": Report, "card_news": CardNews}[etype]
    obj = db.get(model, eid)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대상을 찾을 수 없습니다")
    return obj


def _owner_id(etype: str, obj) -> uuid.UUID | None:
    return obj.author_user_id if etype == "manuscript" else obj.created_by_user_id


def _assert_access(etype: str, obj, user: User) -> None:
    if user.role not in PRIVILEGED and _owner_id(etype, obj) != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "해당 산출물의 작성자 또는 검토자 이상만 처리할 수 있습니다")


@router.get("")
def list_notices(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    out = []
    for n in db.scalars(select(FollowupNotice).order_by(FollowupNotice.created_at.desc())).all():
        imp = svc.impact_summary(db, n)
        out.append(dict(svc.notice_out(n), open_count=sum(1 for rows in imp.values() for r in rows if not r["acked"]),
                        affected_count=sum(len(rows) for rows in imp.values())))
    return out


@router.post("", status_code=status.HTTP_201_CREATED)
def create_notice(payload: NoticeCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = FollowupNotice(
        title=payload.title, original_doc_number=payload.original_doc_number.strip(), original_url=payload.original_url,
        followup_doc_number=payload.followup_doc_number, followup_url=payload.followup_url, followup_org=payload.followup_org,
        followup_published_at=payload.followup_published_at, followup_effective_on=payload.followup_effective_on,
        change_summary=payload.change_summary, changes_json=json.dumps([c.model_dump() for c in payload.changes], ensure_ascii=False),
        is_pilot=payload.is_pilot, created_by_user_id=user.id,
    )
    db.add(n)
    db.flush()
    log_action(db, actor_user_id=user.id, action="followup.create", entity_type="followup_notice", entity_id=n.id,
               detail={"original": n.original_doc_number, "followup": n.followup_doc_number})
    db.commit()
    return dict(svc.notice_out(n), impact=svc.impact_summary(db, n))


@router.post("/detect")
def detect(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """근거로 쓰인 연방관보 문서의 후속 규정 후보를 공식 API에서 찾는다(등록은 연구원이 확인 후)."""
    return {"candidates": svc.detect_candidates(db)}


@router.get("/for/{entity_type}/{entity_id}")
def for_entity(entity_type: Literal["manuscript", "report", "card_news"], entity_id: uuid.UUID,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    obj = _entity(db, entity_type, entity_id)
    _assert_access(entity_type, obj, user)
    return {"open": svc.open_notices_for(db, entity_type, entity_id)}


@router.get("/{notice_id}")
def get_notice(notice_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(FollowupNotice, notice_id)
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알림을 찾을 수 없습니다")
    return dict(svc.notice_out(n), impact=svc.impact_summary(db, n))


@router.post("/{notice_id}/ack")
def ack(notice_id: uuid.UUID, payload: AckBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    n = db.get(FollowupNotice, notice_id)
    if n is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알림을 찾을 수 없습니다")
    obj = _entity(db, payload.entity_type, payload.entity_id)
    _assert_access(payload.entity_type, obj, user)
    if payload.entity_id not in svc.affected_entities(db, n)[payload.entity_type]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "이 알림의 영향 대상이 아닙니다")
    if (payload.entity_type, payload.entity_id) in svc.acked(db, n.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 확인한 항목입니다")
    db.add(FollowupAck(notice_id=n.id, entity_type=payload.entity_type, entity_id=payload.entity_id,
                       resolution=payload.resolution, note=payload.note.strip(), acked_by_user_id=user.id))
    log_action(db, actor_user_id=user.id, action="followup.ack", entity_type=payload.entity_type, entity_id=payload.entity_id,
               detail={"notice_id": str(n.id), "resolution": payload.resolution})
    db.commit()
    return dict(svc.notice_out(n), impact=svc.impact_summary(db, n))
