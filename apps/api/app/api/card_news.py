import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.card_news import (
    CardNews, CardNewsCard, CardNewsElement, CardNewsEvidence, CardNewsExport, CardNewsReview, CardNewsTemplate, CardNewsVersion,
)
from app.models.enums import UserRole
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.report import Report
from app.models.user import User
from app.services import card_news_service as svc
from app.services.card_news_schema import TEMPLATES, element_specs, template_config

router = APIRouter(prefix="/card-news", tags=["card-news"])

PRIVILEGED = (UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)
APPROVERS = (UserRole.ADMIN, UserRole.APPROVER)


# ---------------------------------------------------------------- 요청 모델 ----
class Selection(BaseModel):
    manuscript_id: uuid.UUID
    sentence: str = Field(min_length=1)


class CardNewsCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    template_key: Literal["A", "B", "C", "D"]
    source_type: Literal["report", "summary", "manual"] = "manual"
    source_report_id: uuid.UUID | None = None
    selections: list[Selection] = []
    body_count: int = Field(default=3, ge=1, le=8)
    width_cm: float | None = Field(default=None, ge=4, le=40)
    height_cm: float | None = Field(default=None, ge=6, le=80)


class LockBody(BaseModel):
    lock_version: int


class CardNewsPatch(LockBody):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    template_key: Literal["A", "B", "C", "D"] | None = None
    width_cm: float | None = Field(default=None, ge=4, le=40)
    height_cm: float | None = Field(default=None, ge=6, le=80)


class CardCreate(LockBody):
    kind: Literal["cover", "body", "closing"] = "body"
    after_card_id: uuid.UUID | None = None


class CardPatch(LockBody):
    bg_color: str | None = Field(default=None, pattern=r"^[0-9A-Fa-f]{6}$")
    clear_bg: bool = False


class ReorderBody(LockBody):
    card_ids: list[uuid.UUID]


class ElementPatch(LockBody):
    text: str | None = None
    data: dict[str, Any] | None = None
    style: dict[str, Any] | None = None
    box: dict[str, Any] | None = None
    hidden: bool | None = None


class EvidenceCreate(BaseModel):
    element_key: str
    source_url: str = Field(min_length=1, max_length=1000)
    source_org: str | None = None
    excerpt: str | None = None
    source_footnote_id: uuid.UUID | None = None


class VerifyBody(BaseModel):
    verified: bool = True


class ReviewCreate(BaseModel):
    comment_text: str = Field(min_length=1)
    card_id: uuid.UUID | None = None


class ReviewRequest(BaseModel):
    reviewer_user_id: uuid.UUID | None = None


class ChangesRequest(BaseModel):
    comment_text: str = Field(min_length=1)


class ApproveBody(BaseModel):
    exception_reason: str | None = None


class IitpBody(BaseModel):
    confirmed: bool
    note: str | None = None


class VersionBody(BaseModel):
    change_note: str | None = None


class ExportRequest(BaseModel):
    file_format: Literal["pptx", "png"]
    short_px: int = Field(default=1000, ge=400, le=3000)


class TemplatePatch(BaseModel):
    config: dict[str, Any]


# ---------------------------------------------------------------- 공통 ----
def _get(db: Session, card_news_id: uuid.UUID) -> CardNews:
    cn = db.get(CardNews, card_news_id)
    if cn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "카드뉴스를 찾을 수 없습니다")
    return cn


def _access(cn: CardNews, user: User) -> None:
    if cn.created_by_user_id != user.id and user.role not in PRIVILEGED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "다른 연구원이 만든 카드뉴스에는 접근할 수 없습니다")


def _card(db: Session, cn: CardNews, card_id: uuid.UUID) -> CardNewsCard:
    card = db.get(CardNewsCard, card_id)
    if card is None or card.card_news_id != cn.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "카드를 찾을 수 없습니다")
    return card


def _edit_guard(cn: CardNews, user: User, lock_version: int) -> None:
    _access(cn, user)
    svc.assert_editable(cn)
    svc.assert_lock(cn, lock_version)


def _finish(db: Session, cn: CardNews, user: User, action: str, note: str | None = None, milestone: bool = False) -> dict:
    svc.bump(cn)
    db.flush()
    svc.snapshot(db, cn, user.id, note=note, milestone=milestone)
    log_action(db, actor_user_id=user.id, action=f"card_news.{action}", entity_type="card_news", entity_id=cn.id)
    db.commit()
    db.refresh(cn)
    return svc.detail(db, cn)


# ---------------------------------------------------------------- 템플릿·소스 ----
@router.get("/templates")
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = svc.ensure_templates(db)
    db.commit()
    out = []
    for key, meta in TEMPLATES.items():
        row = rows[key]
        cfg = template_config(key, json.loads(row.config_json or "{}"))
        out.append({
            "key": key, "name": meta["name"], "purpose": meta["purpose"], "version": row.version, "template_id": str(row.id),
            "config": cfg, "elements": {kind: [s.as_dict() for s in element_specs(key, kind)] for kind in ("cover", "body", "closing")},
        })
    return out


@router.post("/templates/{template_key}/new-version", status_code=status.HTTP_201_CREATED)
def new_template_version(template_key: str, payload: TemplatePatch, db: Session = Depends(get_db),
                         user: User = Depends(require_roles(UserRole.ADMIN))):
    if template_key not in TEMPLATES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "템플릿을 찾을 수 없습니다")
    allowed = {"navy", "gray", "green", "accent", "accent_soft", "accent_dark", "accent_light", "bg", "font", "margin_cm", "width_cm", "height_cm"}
    patch = {k: v for k, v in payload.config.items() if k in allowed}
    row = svc.ensure_templates(db)[template_key]
    new = svc.create_template_version(db, row, patch, user.id)
    log_action(db, actor_user_id=user.id, action="card_news_template.new_version", entity_type="card_news_template", entity_id=new.id,
               detail={"version": new.version})
    db.commit()
    return {"key": template_key, "version": new.version, "config": template_config(template_key, json.loads(new.config_json))}


@router.get("/report-sentences/{report_id}")
def report_sentences(report_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = db.get(Report, report_id)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다")
    if report.created_by_user_id != user.id and user.role not in PRIVILEGED:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "다른 연구원의 보고서에는 접근할 수 없습니다")
    return {"report_id": str(report.id), "title": report.title, "report_type": report.report_type,
            "sentences": svc.source_sentences(db, report)}


# ---------------------------------------------------------------- 목록·생성·조회 ----
@router.get("")
def list_card_news(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(CardNews).order_by(CardNews.updated_at.desc())
    if user.role not in PRIVILEGED:
        stmt = stmt.where(CardNews.created_by_user_id == user.id)
    return [{
        "id": str(c.id), "title": c.title, "template_key": c.template_key, "status": c.status, "is_pilot": c.is_pilot,
        "is_synthetic": c.is_synthetic, "source_type": c.source_type, "updated_at": c.updated_at.isoformat(),
        "created_by_user_id": str(c.created_by_user_id),
    } for c in db.scalars(stmt).all()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create(payload: CardNewsCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    report = None
    if payload.source_type in ("report", "summary"):
        if payload.source_report_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "보고서를 선택하세요")
        report = db.get(Report, payload.source_report_id)
        if report is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "보고서를 찾을 수 없습니다")
        if report.created_by_user_id != user.id and user.role not in PRIVILEGED:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "다른 연구원의 보고서에는 접근할 수 없습니다")
        allowed = {s["manuscript_id"] + "|" + svc._norm(s["sentence"]) for s in svc.source_sentences(db, report)}
        for sel in payload.selections:
            if str(sel.manuscript_id) + "|" + svc._norm(sel.sentence) not in allowed:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "선택한 문장이 보고서의 원고에 없습니다 — 문장을 임의로 만들 수 없습니다")
    from app.models.manuscript import Manuscript

    # 시범 작성 원고에서 가져온 카드뉴스는 자동으로 '시범'으로 표시한다
    is_pilot = any((db.get(Manuscript, s.manuscript_id) or Manuscript()).is_pilot for s in payload.selections)
    cn = svc.create_card_news(
        db, user_id=user.id, title=payload.title, template_key=payload.template_key, source_type=payload.source_type,
        source_report_id=payload.source_report_id, selections=[s.model_dump() for s in payload.selections],
        body_count=payload.body_count, width_cm=payload.width_cm, height_cm=payload.height_cm, is_pilot=is_pilot,
    )
    log_action(db, actor_user_id=user.id, action="card_news.create", entity_type="card_news", entity_id=cn.id,
               detail={"template": payload.template_key, "source": payload.source_type})
    db.commit()
    db.refresh(cn)
    return svc.detail(db, cn)


@router.get("/{card_news_id}")
def get_detail(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    return svc.detail(db, cn)


@router.get("/{card_news_id}/scenes")
def get_scenes(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """편집기 미리보기용 장면 목록(PPTX를 만드는 것과 같은 장면 데이터, 빈 요소는 안내 문구로 표시)."""
    cn = _get(db, card_news_id)
    _access(cn, user)
    return {"scenes": svc.build_scenes(db, cn, for_export=False)}


@router.patch("/{card_news_id}")
def patch(card_news_id: uuid.UUID, payload: CardNewsPatch, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    data = payload.model_dump(exclude_unset=True, exclude={"lock_version"})
    if "title" in data:
        cn.title = data["title"]
    if "width_cm" in data and data["width_cm"]:
        cn.width_cm = data["width_cm"]
    if "height_cm" in data and data["height_cm"]:
        cn.height_cm = data["height_cm"]
    if data.get("template_key"):
        svc.change_template(db, cn, data["template_key"])
    return _finish(db, cn, user, "update", note="템플릿·제목·크기 변경" if data.get("template_key") else None,
                   milestone=bool(data.get("template_key")))


@router.post("/{card_news_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """내부 확정된 카드뉴스를 고치려면 승인 취소 대신 '새 수정 버전(복사본)'을 만들 수 있다. 원본·출력본은 그대로 보존된다."""
    src = _get(db, card_news_id)
    _access(src, user)
    new = CardNews(
        title=f"{src.title} (수정본)", template_key=src.template_key, template_id=src.template_id, width_cm=src.width_cm,
        height_cm=src.height_cm, source_type=src.source_type, source_report_id=src.source_report_id,
        source_versions_json=src.source_versions_json, is_pilot=src.is_pilot, is_synthetic=src.is_synthetic,
        parent_card_news_id=src.id, created_by_user_id=user.id, status="draft",
    )
    db.add(new)
    db.flush()
    id_map: dict[uuid.UUID, uuid.UUID] = {}
    for card in svc._cards(db, src):
        nc = CardNewsCard(card_news_id=new.id, kind=card.kind, position=card.position, bg_color=card.bg_color)
        db.add(nc)
        db.flush()
        id_map[card.id] = nc.id
        for el in svc._elements(db, card).values():
            db.add(CardNewsElement(card_id=nc.id, key=el.key, element_type=el.element_type, text=el.text, data_json=el.data_json,
                                   style_json=el.style_json, box_json=el.box_json, hidden=el.hidden,
                                   source_manuscript_id=el.source_manuscript_id, source_sentence=el.source_sentence))
    for ev in db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_news_id == src.id)).all():
        db.add(CardNewsEvidence(
            card_news_id=new.id, card_id=id_map[ev.card_id], element_key=ev.element_key, source_manuscript_id=ev.source_manuscript_id,
            source_footnote_id=ev.source_footnote_id, source_document_id=ev.source_document_id, source_url=ev.source_url,
            source_org=ev.source_org, excerpt=ev.excerpt, original_footnote_status=ev.original_footnote_status,
            source_lock_version=ev.source_lock_version, verification_status=ev.verification_status,
            verified_text_hash=ev.verified_text_hash, verified_by_user_id=ev.verified_by_user_id, verified_at=ev.verified_at,
            created_by_user_id=user.id))
    db.flush()
    svc.snapshot(db, new, user.id, note=f"'{src.title}'에서 복사한 새 수정 버전", milestone=True)
    log_action(db, actor_user_id=user.id, action="card_news.duplicate", entity_type="card_news", entity_id=new.id,
               detail={"parent": str(src.id)})
    db.commit()
    db.refresh(new)
    return svc.detail(db, new)


# ---------------------------------------------------------------- 카드·요소 편집 ----
@router.post("/{card_news_id}/cards", status_code=status.HTTP_201_CREATED)
def add_card(card_news_id: uuid.UUID, payload: CardCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    cards = svc._cards(db, cn)
    pos = len(cards)
    if payload.after_card_id:
        after = _card(db, cn, payload.after_card_id)
        pos = after.position + 1
    for c in cards:
        if c.position >= pos:
            c.position += 1
    svc._new_card(db, cn, payload.kind, pos)
    return _finish(db, cn, user, "card_add", note="카드 추가")


@router.delete("/{card_news_id}/cards/{card_id}")
def delete_card(card_news_id: uuid.UUID, card_id: uuid.UUID, lock_version: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, lock_version)
    card = _card(db, cn, card_id)
    cards = svc._cards(db, cn)
    if len(cards) <= 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "카드는 최소 1장이 필요합니다")
    for ev in db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_id == card.id)).all():
        db.delete(ev)
    for rv in db.scalars(select(CardNewsReview).where(CardNewsReview.card_id == card.id)).all():
        rv.card_id = None
    for el in svc._elements(db, card).values():
        db.delete(el)
    db.delete(card)
    db.flush()
    for i, c in enumerate(svc._cards(db, cn)):
        c.position = i
    return _finish(db, cn, user, "card_delete", note="카드 삭제", milestone=True)


@router.post("/{card_news_id}/cards/{card_id}/duplicate", status_code=status.HTTP_201_CREATED)
def duplicate_card(card_news_id: uuid.UUID, card_id: uuid.UUID, payload: LockBody, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    card = _card(db, cn, card_id)
    for c in svc._cards(db, cn):
        if c.position > card.position:
            c.position += 1
    nc = CardNewsCard(card_news_id=cn.id, kind=card.kind, position=card.position + 1, bg_color=card.bg_color)
    db.add(nc)
    db.flush()
    for el in svc._elements(db, card).values():
        db.add(CardNewsElement(card_id=nc.id, key=el.key, element_type=el.element_type, text=el.text, data_json=el.data_json,
                               style_json=el.style_json, box_json=el.box_json, hidden=el.hidden,
                               source_manuscript_id=el.source_manuscript_id, source_sentence=el.source_sentence))
    for ev in db.scalars(select(CardNewsEvidence).where(CardNewsEvidence.card_id == card.id)).all():
        db.add(CardNewsEvidence(
            card_news_id=cn.id, card_id=nc.id, element_key=ev.element_key, source_manuscript_id=ev.source_manuscript_id,
            source_footnote_id=ev.source_footnote_id, source_document_id=ev.source_document_id, source_url=ev.source_url,
            source_org=ev.source_org, excerpt=ev.excerpt, original_footnote_status=ev.original_footnote_status,
            source_lock_version=ev.source_lock_version, verification_status=ev.verification_status,
            verified_text_hash=ev.verified_text_hash, verified_by_user_id=ev.verified_by_user_id, verified_at=ev.verified_at,
            created_by_user_id=user.id))
    return _finish(db, cn, user, "card_duplicate", note="카드 복제")


@router.post("/{card_news_id}/cards/reorder")
def reorder_cards(card_news_id: uuid.UUID, payload: ReorderBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    cards = {c.id: c for c in svc._cards(db, cn)}
    if set(payload.card_ids) != set(cards):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "모든 카드의 ID를 정확히 한 번씩 보내야 합니다")
    for pos, cid in enumerate(payload.card_ids):
        cards[cid].position = pos
    return _finish(db, cn, user, "card_reorder", note="카드 순서 변경")


@router.patch("/{card_news_id}/cards/{card_id}")
def patch_card(card_news_id: uuid.UUID, card_id: uuid.UUID, payload: CardPatch, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    card = _card(db, cn, card_id)
    if payload.clear_bg:
        card.bg_color = None
    elif payload.bg_color:
        card.bg_color = payload.bg_color.upper()
    return _finish(db, cn, user, "card_update")


@router.patch("/{card_news_id}/cards/{card_id}/elements/{key}")
def patch_element(card_news_id: uuid.UUID, card_id: uuid.UUID, key: str, payload: ElementPatch, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    card = _card(db, cn, card_id)
    el = svc._elements(db, card).get(key)
    if el is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "요소를 찾을 수 없습니다")
    data = payload.model_dump(exclude_unset=True, exclude={"lock_version"})
    if "text" in data and data["text"] is not None:
        if el.element_type == "choice":
            from app.services.card_news_schema import STAGE_KINDS

            if data["text"] not in STAGE_KINDS:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "허용되지 않은 선택값입니다")
        el.text = data["text"]
    if "data" in data:
        el.data_json = json.dumps(data["data"], ensure_ascii=False) if data["data"] is not None else None
    if "style" in data:
        el.style_json = json.dumps(data["style"], ensure_ascii=False) if data["style"] else None
    if "box" in data:
        el.box_json = json.dumps(data["box"], ensure_ascii=False) if data["box"] else None
    if "hidden" in data and data["hidden"] is not None:
        el.hidden = data["hidden"]
    return _finish(db, cn, user, "element_update")


# ---------------------------------------------------------------- 원문 근거 ----
@router.post("/{card_news_id}/cards/{card_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence(card_news_id: uuid.UUID, card_id: uuid.UUID, payload: EvidenceCreate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    svc.assert_editable(cn)
    card = _card(db, cn, card_id)
    if payload.element_key not in {s.key for s in element_specs(cn.template_key, card.kind) if s.evidence}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "근거를 연결할 수 없는 요소입니다")
    if payload.source_footnote_id:
        fn = db.get(ManuscriptFootnote, payload.source_footnote_id)
        if fn is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "원고 각주를 찾을 수 없습니다")
        svc.add_evidence_from_footnote(db, cn, card, payload.element_key, fn, user.id)
    else:
        db.add(CardNewsEvidence(card_news_id=cn.id, card_id=card.id, element_key=payload.element_key, source_url=payload.source_url,
                                source_org=payload.source_org, excerpt=payload.excerpt, verification_status="not_verified",
                                created_by_user_id=user.id))
    log_action(db, actor_user_id=user.id, action="card_news.evidence_add", entity_type="card_news", entity_id=cn.id)
    db.commit()
    return svc.detail(db, cn)


def _evidence(db: Session, cn: CardNews, evidence_id: uuid.UUID) -> CardNewsEvidence:
    ev = db.get(CardNewsEvidence, evidence_id)
    if ev is None or ev.card_news_id != cn.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "근거를 찾을 수 없습니다")
    return ev


@router.post("/{card_news_id}/evidence/{evidence_id}/verify")
def verify_evidence(card_news_id: uuid.UUID, evidence_id: uuid.UUID, payload: VerifyBody, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    """연구원이 원문과 카드 내용을 직접 대조한 뒤에만 호출한다. 이 시점의 요소 텍스트 해시를 저장한다."""
    cn = _get(db, card_news_id)
    _access(cn, user)
    svc.assert_editable(cn)
    ev = _evidence(db, cn, evidence_id)
    el = db.scalars(select(CardNewsElement).where(CardNewsElement.card_id == ev.card_id, CardNewsElement.key == ev.element_key)).first()
    if payload.verified:
        ev.verification_status = "verified"
        ev.verified_text_hash = svc.text_hash(el.text if el else None, svc._load_json(el.data_json) if el else None)
        ev.verified_by_user_id, ev.verified_at = user.id, datetime.now(timezone.utc)
    else:
        ev.verification_status, ev.verified_text_hash, ev.verified_by_user_id, ev.verified_at = "not_verified", None, None, None
    log_action(db, actor_user_id=user.id, action="card_news.evidence_verify", entity_type="card_news", entity_id=cn.id,
               detail={"evidence_id": str(ev.id), "verified": payload.verified})
    db.commit()
    return svc.detail(db, cn)


@router.delete("/{card_news_id}/evidence/{evidence_id}")
def delete_evidence(card_news_id: uuid.UUID, evidence_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    svc.assert_editable(cn)
    db.delete(_evidence(db, cn, evidence_id))
    db.commit()
    return svc.detail(db, cn)


# ---------------------------------------------------------------- 버전 ----
@router.get("/{card_news_id}/versions")
def list_versions(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    rows = db.scalars(select(CardNewsVersion).where(CardNewsVersion.card_news_id == cn.id).order_by(CardNewsVersion.version_no.desc())).all()
    return [{"id": str(v.id), "version_no": v.version_no, "change_note": v.change_note, "is_milestone": v.is_milestone,
             "edited_by_user_id": str(v.edited_by_user_id), "created_at": v.created_at.isoformat()} for v in rows]


@router.post("/{card_news_id}/versions", status_code=status.HTTP_201_CREATED)
def save_milestone(card_news_id: uuid.UUID, payload: VersionBody, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    svc.snapshot(db, cn, user.id, note=payload.change_note or "주요 버전 저장", milestone=True)
    db.commit()
    return list_versions(card_news_id, db, user)


@router.post("/{card_news_id}/versions/{version_id}/restore")
def restore(card_news_id: uuid.UUID, version_id: uuid.UUID, payload: LockBody, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _edit_guard(cn, user, payload.lock_version)
    ver = db.get(CardNewsVersion, version_id)
    if ver is None or ver.card_news_id != cn.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "버전을 찾을 수 없습니다")
    svc.restore_version(db, cn, ver, user.id)
    return _finish(db, cn, user, "restore", note=f"v{ver.version_no} 복원", milestone=True)


# ---------------------------------------------------------------- 검토·승인 ----
@router.get("/{card_news_id}/reviews")
def list_reviews(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    rows = db.scalars(select(CardNewsReview).where(CardNewsReview.card_news_id == cn.id).order_by(CardNewsReview.created_at)).all()
    return [{"id": str(r.id), "card_id": str(r.card_id) if r.card_id else None, "author_user_id": str(r.author_user_id),
             "comment_text": r.comment_text, "status": r.status, "created_at": r.created_at.isoformat()} for r in rows]


@router.post("/{card_news_id}/reviews", status_code=status.HTTP_201_CREATED)
def add_review(card_news_id: uuid.UUID, payload: ReviewCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    if payload.card_id:
        _card(db, cn, payload.card_id)
    db.add(CardNewsReview(card_news_id=cn.id, card_id=payload.card_id, author_user_id=user.id, comment_text=payload.comment_text))
    db.commit()
    return list_reviews(card_news_id, db, user)


@router.post("/{card_news_id}/reviews/{review_id}/resolve")
def resolve_review(card_news_id: uuid.UUID, review_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    rv = db.get(CardNewsReview, review_id)
    if rv is None or rv.card_news_id != cn.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "검토 의견을 찾을 수 없습니다")
    rv.status, rv.resolved_by_user_id, rv.resolved_at = "resolved", user.id, datetime.now(timezone.utc)
    db.commit()
    return list_reviews(card_news_id, db, user)


@router.post("/{card_news_id}/request-review")
def request_review(card_news_id: uuid.UUID, payload: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    if cn.status not in ("draft", "changes_requested"):
        raise HTTPException(status.HTTP_409_CONFLICT, "초안 또는 수정 요청 상태에서만 검토를 요청할 수 있습니다")
    if payload.reviewer_user_id:
        reviewer = db.get(User, payload.reviewer_user_id)
        if reviewer is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "검토자를 찾을 수 없습니다")
        cn.reviewer_user_id = reviewer.id
    cn.status = "review_requested"
    svc.snapshot(db, cn, user.id, note="검토 요청", milestone=True)
    log_action(db, actor_user_id=user.id, action="card_news.request_review", entity_type="card_news", entity_id=cn.id)
    db.commit()
    return svc.detail(db, cn)


@router.post("/{card_news_id}/request-changes")
def request_changes(card_news_id: uuid.UUID, payload: ChangesRequest, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(*PRIVILEGED))):
    cn = _get(db, card_news_id)
    if cn.status != "review_requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "검토 요청 상태에서만 수정을 요청할 수 있습니다")
    cn.status = "changes_requested"
    db.add(CardNewsReview(card_news_id=cn.id, author_user_id=user.id, comment_text=payload.comment_text))
    log_action(db, actor_user_id=user.id, action="card_news.request_changes", entity_type="card_news", entity_id=cn.id)
    db.commit()
    return svc.detail(db, cn)


@router.post("/{card_news_id}/approve")
def approve(card_news_id: uuid.UUID, payload: ApproveBody, db: Session = Depends(get_db), user: User = Depends(require_roles(*APPROVERS))):
    cn = _get(db, card_news_id)
    if cn.status != "review_requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "검토 요청된 카드뉴스만 내부 확정할 수 있습니다")
    issues = svc.run_preflight(db, cn)
    block = svc.blocking(issues)
    reason = (payload.exception_reason or "").strip()
    open_reviews = db.scalars(select(CardNewsReview).where(CardNewsReview.card_news_id == cn.id, CardNewsReview.status == "open")).all()
    if (block or open_reviews) and not reason:
        problems = [b["message"] for b in block] + ([f"미해결 검토 의견 {len(open_reviews)}건"] if open_reviews else [])
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={
            "message": "필수 점검을 통과하지 못해 내부 확정할 수 없습니다 — 해결하거나 승인권자 예외 사유를 입력하세요",
            "blocking": [{"message": m} for m in problems]})
    cn.status = "approved"
    cn.approve_exception_reason = reason or None
    cn.approved_by_user_id, cn.approved_at = user.id, datetime.now(timezone.utc)
    svc.bump(cn)
    svc.snapshot(db, cn, user.id, note="내부 확정", milestone=True)
    log_action(db, actor_user_id=user.id, action="card_news.approve", entity_type="card_news", entity_id=cn.id,
               detail={"exception_reason": reason or None, "blocking_codes": [b["code"] for b in block]})
    db.commit()
    db.refresh(cn)
    return svc.detail(db, cn)


@router.post("/{card_news_id}/reopen")
def reopen(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(require_roles(*APPROVERS))):
    cn = _get(db, card_news_id)
    if cn.status != "approved":
        raise HTTPException(status.HTTP_409_CONFLICT, "내부 확정된 카드뉴스만 해제할 수 있습니다")
    cn.status = "draft"
    svc.bump(cn)
    log_action(db, actor_user_id=user.id, action="card_news.reopen", entity_type="card_news", entity_id=cn.id)
    db.commit()
    db.refresh(cn)
    return svc.detail(db, cn)


@router.patch("/{card_news_id}/iitp")
def set_iitp(card_news_id: uuid.UUID, payload: IitpBody, db: Session = Depends(get_db), user: User = Depends(require_roles(*APPROVERS))):
    """IITP 공식 확인 여부 — 내부 확정과 별개로 기록한다."""
    cn = _get(db, card_news_id)
    cn.iitp_confirmed, cn.iitp_note = payload.confirmed, payload.note
    log_action(db, actor_user_id=user.id, action="card_news.iitp", entity_type="card_news", entity_id=cn.id,
               detail={"confirmed": payload.confirmed})
    db.commit()
    return svc.detail(db, cn)


# ---------------------------------------------------------------- 출력 ----
@router.get("/{card_news_id}/exports")
def list_exports(card_news_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    rows = db.scalars(select(CardNewsExport).where(CardNewsExport.card_news_id == cn.id).order_by(CardNewsExport.created_at.desc())).all()
    return [svc.export_out(e) for e in rows]


@router.post("/{card_news_id}/exports", status_code=status.HTTP_201_CREATED)
def create_export(card_news_id: uuid.UUID, payload: ExportRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    try:
        export = svc.generate_export(db, cn, file_format=payload.file_format, user_id=user.id, short_px=payload.short_px)
    except svc.ExportInProgressError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    log_action(db, actor_user_id=user.id, action="card_news.export", entity_type="card_news", entity_id=cn.id,
               detail={"format": payload.file_format, "export_id": str(export.id), "status": export.status})
    db.commit()
    return svc.export_out(export)


def _export_row(db: Session, cn: CardNews, export_id: uuid.UUID) -> CardNewsExport:
    e = db.get(CardNewsExport, export_id)
    if e is None or e.card_news_id != cn.id or e.status != "success" or not e.file_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "다운로드할 수 있는 출력본이 없습니다")
    return e


@router.get("/{card_news_id}/exports/{export_id}/download")
def download(card_news_id: uuid.UUID, export_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    e = _export_row(db, cn, export_id)
    media = ("application/vnd.openxmlformats-officedocument.presentationml.presentation" if e.file_format == "pptx" else "application/zip")
    return FileResponse(e.file_path, media_type=media, filename=e.file_name or f"cardnews.{e.file_format}")


@router.get("/{card_news_id}/exports/{export_id}/cards/{number}.png")
def download_card_png(card_news_id: uuid.UUID, export_id: uuid.UUID, number: int, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    cn = _get(db, card_news_id)
    _access(cn, user)
    e = _export_row(db, cn, export_id)
    path = svc.export_dir() / f"{e.id}_png" / f"card-{number:02d}.png"
    if e.file_format != "png" or not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "해당 카드의 PNG가 없습니다")
    return FileResponse(str(path), media_type="image/png", filename=f"card-{number:02d}.png")
