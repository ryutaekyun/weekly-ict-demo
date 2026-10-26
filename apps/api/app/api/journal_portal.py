"""주간기술동향지 외부 포털 API — 외부 저자(author)와 검토자(reviewer·ext_reviewer) 전용.

저자는 자신에게 의뢰된 건과 자신의 원고만, 검토자는 자신에게 배정된 원고만 볼 수 있다(소유·배정은 서버에서 매번 확인).
저자에게는 검토자 이름을 보여주지 않는다('검토자').
"""

import json
import uuid
from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.enums import UserRole
from app.models.journal import (
    JournalAssignment, JournalAttachment, JournalCommission, JournalComment, JournalExpert, JournalManuscript, JournalVersion,
)
from app.models.user import User
from app.services import journal_files
from app.services import journal_service as svc

router = APIRouter(prefix="/journal/portal", tags=["journal-portal"])
author_only = require_roles(UserRole.AUTHOR)
reviewer_roles = require_roles(UserRole.REVIEWER, UserRole.EXT_REVIEWER, UserRole.APPROVER)


def _audit(db: Session, user: User, action: str, entity_id: uuid.UUID, **detail) -> None:
    log_action(db, actor_user_id=user.id, action=f"journal.portal.{action}", entity_type="journal_manuscript", entity_id=entity_id, detail=detail or None)


def _file(path: str, name: str, mime: str | None) -> Response:
    try:
        data = journal_files.read(path)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")
    return Response(content=data, media_type=mime or "application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------- 저자 ----
def _my_expert(db: Session, user: User) -> JournalExpert:
    expert = db.scalar(select(JournalExpert).where(JournalExpert.user_id == user.id))
    if expert is None or expert.anonymized:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "연결된 전문가 정보가 없습니다 — 편집 담당자에게 문의하세요")
    return expert


def _my_commission(db: Session, user: User, cid: uuid.UUID) -> JournalCommission:
    expert = _my_expert(db, user)
    c = db.get(JournalCommission, cid)
    if c is None or c.expert_id != expert.id or c.status in ("draft", "ready"):  # 아직 의뢰하지 않은 건은 저자에게 보이지 않는다
        raise HTTPException(status.HTTP_404_NOT_FOUND, "의뢰를 찾을 수 없습니다")
    return c


def _my_manuscript(db: Session, user: User, mid: uuid.UUID) -> JournalManuscript:
    expert = _my_expert(db, user)
    ms = db.get(JournalManuscript, mid)
    if ms is None or ms.expert_id != expert.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "원고를 찾을 수 없습니다")  # 다른 저자의 원고는 존재 여부도 알려주지 않는다
    return ms


def _commission_view(db: Session, c: JournalCommission) -> dict:
    ms = db.scalar(select(JournalManuscript).where(JournalManuscript.commission_id == c.id))
    issue = svc.issue_label(db.get(svc.JournalIssue, c.issue_id))
    return {"id": str(c.id), "issue_label": issue, "topic": c.topic, "purpose": c.purpose, "outline": c.outline, "length_spec": c.length_spec,
            "format_spec": c.format_spec, "due_date": c.due_date.isoformat() if c.due_date else None, "delivery_method": c.delivery_method,
            "contact_info": c.contact_info, "status": c.status, "status_label": svc.COMMISSION_STATUS_LABELS[c.status],
            "manuscript_id": str(ms.id) if ms else None, "manuscript_status": svc.STATUS_LABELS.get(ms.status) if ms else None,
            "can_respond": c.status in ("requested", "no_response"), "can_submit": c.status == "accepted" and (ms is None or ms.status == "format_fix_needed" or ms.version_count == 0)}


@router.get("/author/commissions")
def my_commissions(db: Session = Depends(get_db), user: User = Depends(author_only)):
    expert = _my_expert(db, user)
    rows = db.scalars(select(JournalCommission).where(JournalCommission.expert_id == expert.id,
                                                      JournalCommission.status.notin_(["draft", "ready"])).order_by(JournalCommission.created_at.desc())).all()
    return [_commission_view(db, c) for c in rows]


class RespondIn(BaseModel):
    response: Literal["accept", "decline"]
    note: str | None = None


@router.post("/author/commissions/{cid}/respond")
def respond(cid: uuid.UUID, payload: RespondIn, db: Session = Depends(get_db), user: User = Depends(author_only)):
    c = _my_commission(db, user, cid)
    if c.status not in ("requested", "no_response"):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 응답한 의뢰입니다")
    svc.change_commission_status(db, c, "accepted" if payload.response == "accept" else "declined", user.id, payload.note)
    log_action(db, actor_user_id=user.id, action="journal.portal.respond", entity_type="journal_commission", entity_id=c.id, detail={"response": payload.response})
    db.commit()
    return _commission_view(db, c)


def _author_manuscript_view(db: Session, ms: JournalManuscript) -> dict:
    out = svc.manuscript_out(db, ms, for_author=True)
    for v in out["versions"]:  # 저자에게는 파일 경로·보안 검사 세부를 숨기고 형식 점검 결과만 보여준다
        v.pop("scan", None)
    out.pop("expert_id", None)
    return out


@router.get("/author/manuscripts")
def my_manuscripts(db: Session = Depends(get_db), user: User = Depends(author_only)):
    expert = _my_expert(db, user)
    rows = db.scalars(select(JournalManuscript).where(JournalManuscript.expert_id == expert.id).order_by(JournalManuscript.created_at.desc())).all()
    return [{"id": str(m.id), "title": m.title, "issue_label": svc.issue_label(db.get(svc.JournalIssue, m.issue_id)), "status": m.status,
             "status_label": svc.STATUS_LABELS[m.status], "version_count": m.version_count} for m in rows]


@router.get("/author/manuscripts/{mid}")
def my_manuscript(mid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(author_only)):
    return _author_manuscript_view(db, _my_manuscript(db, user, mid))


@router.post("/author/commissions/{cid}/submit", status_code=status.HTTP_201_CREATED)
def submit_manuscript(
    cid: uuid.UUID, file: UploadFile = File(...), title: str = Form(...), title_en: str | None = Form(None), summary: str | None = Form(None),
    authors_json: str = Form("[]"), references_text: str | None = Form(None), copyright_confirmed: bool = Form(False),
    third_party_note: str | None = Form(None), note: str | None = Form(None),
    db: Session = Depends(get_db), user: User = Depends(author_only),
):
    """수락한 의뢰의 원고를 제출한다. 형식 보완 요청을 받은 경우 같은 경로로 다시 제출한다(덮어쓰지 않고 새 버전)."""
    c = _my_commission(db, user, cid)
    if c.status != "accepted":
        raise HTTPException(status.HTTP_409_CONFLICT, "집필을 수락한 의뢰만 원고를 제출할 수 있습니다")
    ms = svc.ensure_manuscript_for_commission(db, c, user.id)
    if ms.version_count > 0 and ms.status != "format_fix_needed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 제출된 원고입니다 — 수정 요청을 받은 뒤 수정본으로 제출하세요")
    try:
        authors = json.loads(authors_json)
        assert isinstance(authors, list)
    except (ValueError, AssertionError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "저자 정보 형식이 올바르지 않습니다")
    if not title.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "원고 제목을 입력하세요")
    ms.title, ms.title_en, ms.summary, ms.references_text = title.strip(), title_en, summary, references_text
    ms.authors_json = json.dumps(authors, ensure_ascii=False)
    ms.copyright_confirmed, ms.third_party_note = copyright_confirmed, third_party_note
    cfg = svc.get_settings(db)
    limit = int(cfg["max_upload_mb"]) * 1024 * 1024
    data = file.file.read(limit + 1)
    try:
        ver = svc.submit_version(db, ms, user, file.filename or "manuscript", data, "submission", note)
    except journal_files.UploadRejected as exc:
        _audit(db, user, "upload.rejected", ms.id, reason=str(exc), file=file.filename)
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if ms.status == "format_fix_needed":
        ms.status = "received"  # 보완본 재접수 → 형식 점검을 다시 거친다
    svc.apply_submission_status(ms, ver)
    _audit(db, user, "submit", ms.id, version=ver.version_no, format_result=ms.format_status)
    db.commit()
    return _author_manuscript_view(db, ms)


class ReplyIn(BaseModel):
    text: str = Field(min_length=1)


@router.post("/author/manuscripts/{mid}/comments/{cid}/reply")
def reply_comment(mid: uuid.UUID, cid: uuid.UUID, payload: ReplyIn, db: Session = Depends(get_db), user: User = Depends(author_only)):
    ms = _my_manuscript(db, user, mid)
    c = db.get(JournalComment, cid)
    if c is None or c.manuscript_id != ms.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "의견을 찾을 수 없습니다")
    if ms.status not in ("revision_requested", "format_fix_needed"):
        raise HTTPException(status.HTTP_409_CONFLICT, "수정 요청 상태에서만 답변할 수 있습니다")
    c.author_reply, c.replied_by_user_id, c.replied_at = payload.text, user.id, svc.now()
    if c.status == "open":
        c.status = "answered"  # 답변했을 뿐 '해결'은 담당자·검토자가 확인한 뒤에만 된다
    _audit(db, user, "reply", ms.id, comment=str(c.id))
    db.commit()
    return svc.comment_out(db, c, anonymize=True)


@router.post("/author/manuscripts/{mid}/revision", status_code=status.HTTP_201_CREATED)
def submit_revision(mid: uuid.UUID, file: UploadFile = File(...), note: str | None = Form(None), db: Session = Depends(get_db),
                    user: User = Depends(author_only)):
    ms = _my_manuscript(db, user, mid)
    if ms.status != "revision_requested":
        raise HTTPException(status.HTTP_409_CONFLICT, "수정 요청을 받은 원고만 수정본을 제출할 수 있습니다")
    cfg = svc.get_settings(db)
    limit = int(cfg["max_upload_mb"]) * 1024 * 1024
    data = file.file.read(limit + 1)
    try:
        ver = svc.submit_version(db, ms, user, file.filename or "revision", data, "revision", note)
    except journal_files.UploadRejected as exc:
        _audit(db, user, "upload.rejected", ms.id, reason=str(exc), file=file.filename)
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    for c in db.scalars(select(JournalComment).where(JournalComment.manuscript_id == ms.id, JournalComment.status == "answered",
                                                     JournalComment.reply_version_id.is_(None))).all():
        c.reply_version_id = ver.id
    svc.apply_submission_status(ms, ver)
    _audit(db, user, "revision", ms.id, version=ver.version_no)
    db.commit()
    return _author_manuscript_view(db, ms)


@router.post("/author/manuscripts/{mid}/attachments", status_code=status.HTTP_201_CREATED)
def author_attachment(mid: uuid.UUID, doc_type: str = Form(...), file: UploadFile = File(...), note: str | None = Form(None),
                      db: Session = Depends(get_db), user: User = Depends(author_only)):
    ms = _my_manuscript(db, user, mid)
    cfg = svc.get_settings(db)
    limit = int(cfg["max_upload_mb"]) * 1024 * 1024
    data = file.file.read(limit + 1)
    try:
        scan = journal_files.scan_upload(file.filename or "attachment", data, cfg["attachment_ext"], limit)
    except journal_files.UploadRejected as exc:
        _audit(db, user, "upload.rejected", ms.id, reason=str(exc), file=file.filename)
        db.commit()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    path, digest = journal_files.store("attachments", ms.id, file.filename or "attachment", data)
    last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no.desc()))
    db.add(JournalAttachment(manuscript_id=ms.id, version_id=last.id if last else None, doc_type=doc_type, file_name=journal_files.safe_name(file.filename or "attachment"),
                             file_path=path, file_size=len(data), sha256=digest, scan_json=json.dumps(scan, ensure_ascii=False), note=note,
                             uploaded_by_user_id=user.id))
    ms.lock_version += 1
    _audit(db, user, "attachment", ms.id, doc_type=doc_type)
    db.commit()
    return _author_manuscript_view(db, ms)


@router.get("/author/manuscripts/{mid}/versions/{vid}/download")
def author_download(mid: uuid.UUID, vid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(author_only)):
    ms = _my_manuscript(db, user, mid)
    ver = db.get(JournalVersion, vid)
    if ver is None or ver.manuscript_id != ms.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "버전을 찾을 수 없습니다")
    _audit(db, user, "download", ms.id, version=ver.version_no)
    db.commit()
    return _file(ver.file_path, ver.file_name, ver.mime)


# ---------------------------------------------------------------- 검토자 ----
def _my_assignment(db: Session, user: User, aid: uuid.UUID) -> JournalAssignment:
    a = db.get(JournalAssignment, aid)
    if a is None or a.reviewer_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "배정을 찾을 수 없습니다")  # 미배정 원고는 존재 여부도 알려주지 않는다
    return a


def _review_view(db: Session, a: JournalAssignment) -> dict:
    ms = db.get(JournalManuscript, a.manuscript_id)
    versions = list(db.scalars(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id).order_by(JournalVersion.version_no)).all())
    comments = db.scalars(select(JournalComment).where(JournalComment.manuscript_id == ms.id, JournalComment.author_user_id == a.reviewer_user_id)
                          .order_by(JournalComment.created_at)).all()
    cfg = svc.get_settings(db)
    return {
        "assignment": svc.assignment_out(db, a),
        "manuscript": {"id": str(ms.id), "title": ms.title, "title_en": ms.title_en, "summary": ms.summary, "authors": json.loads(ms.authors_json or "[]"),
                       "status": ms.status, "status_label": svc.STATUS_LABELS[ms.status], "references_text": ms.references_text,
                       "issue_label": svc.issue_label(db.get(svc.JournalIssue, ms.issue_id))},
        "versions": [{"id": str(v.id), "version_no": v.version_no, "kind": v.kind, "file_name": v.file_name, "uploaded_at": v.created_at.isoformat(),
                      "note": v.note, "words": json.loads(v.extract_json or "{}").get("words")} for v in versions if v.kind != "proofread"],
        "comments": [svc.comment_out(db, c, anonymize=False) for c in comments],
        "outcomes": cfg["decision_outcomes"],
        "notice": "검토 의견과 추천은 심의 담당자의 참고 의견이며, 게재 여부는 심의 담당자가 확정합니다",
    }


@router.get("/reviews")
def my_reviews(db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    rows = db.scalars(select(JournalAssignment).where(JournalAssignment.reviewer_user_id == user.id).order_by(JournalAssignment.created_at.desc())).all()
    out = []
    for a in rows:
        ms = db.get(JournalManuscript, a.manuscript_id)
        out.append({**svc.assignment_out(db, a), "title": ms.title, "manuscript_status": svc.STATUS_LABELS[ms.status],
                    "issue_label": svc.issue_label(db.get(svc.JournalIssue, ms.issue_id))})
    return out


@router.get("/reviews/{aid}")
def review_detail(aid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    a = _my_assignment(db, user, aid)
    if a.status == "assigned":
        a.status = "in_progress"
    _audit(db, user, "review.open", a.manuscript_id)
    db.commit()
    return _review_view(db, a)


@router.get("/reviews/{aid}/versions/{vid}/download")
def review_download(aid: uuid.UUID, vid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    a = _my_assignment(db, user, aid)
    ver = db.get(JournalVersion, vid)
    if ver is None or ver.manuscript_id != a.manuscript_id or ver.kind == "proofread":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "버전을 찾을 수 없습니다")
    _audit(db, user, "review.download", a.manuscript_id, version=ver.version_no)
    db.commit()
    return _file(ver.file_path, ver.file_name, ver.mime)


class ConflictIn(BaseModel):
    declared: bool
    note: str | None = None


@router.post("/reviews/{aid}/conflict")
def declare_conflict(aid: uuid.UUID, payload: ConflictIn, db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    a = _my_assignment(db, user, aid)
    if a.status == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 완료된 검토입니다")
    a.conflict_declared, a.conflict_checked, a.conflict_note = payload.declared, True, payload.note
    _audit(db, user, "review.conflict", a.manuscript_id, declared=payload.declared)
    db.commit()
    return _review_view(db, a)


class ReviewComment(BaseModel):
    scope: Literal["doc", "paragraph", "table", "figure"] = "doc"
    anchor_text: str | None = None
    anchor_index: int | None = None
    text: str = Field(min_length=1)
    requires_revision: bool = True


@router.post("/reviews/{aid}/comments", status_code=status.HTTP_201_CREATED)
def review_comment(aid: uuid.UUID, payload: ReviewComment, db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    a = _my_assignment(db, user, aid)
    if a.status == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 완료된 검토입니다")
    if a.conflict_declared:
        raise HTTPException(status.HTTP_409_CONFLICT, "이해상충을 신고한 배정에는 의견을 작성할 수 없습니다 — 편집 담당자에게 문의하세요")
    ms = db.get(JournalManuscript, a.manuscript_id)
    last = db.scalar(select(JournalVersion).where(JournalVersion.manuscript_id == ms.id, JournalVersion.kind != "proofread")
                     .order_by(JournalVersion.version_no.desc()))
    c = JournalComment(manuscript_id=ms.id, version_id=last.id if last else None, assignment_id=a.id, author_user_id=user.id, kind="review",
                       **payload.model_dump())
    db.add(c)
    if a.status == "assigned":
        a.status = "in_progress"
    db.flush()
    _audit(db, user, "review.comment", ms.id, scope=payload.scope)
    db.commit()
    return svc.comment_out(db, c, anonymize=False)


@router.post("/reviews/{aid}/comments/{cid}/resolve")
def review_resolve(aid: uuid.UUID, cid: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    """검토자가 저자의 답변·수정본을 확인하고 자신이 남긴 의견을 해결 처리한다."""
    a = _my_assignment(db, user, aid)
    c = db.get(JournalComment, cid)
    if c is None or c.assignment_id != a.id or c.author_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "의견을 찾을 수 없습니다")
    if c.status == "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "저자 답변이 없는 의견은 해결 처리할 수 없습니다")
    c.status, c.resolved_by_user_id, c.resolved_at = "resolved", user.id, svc.now()
    _audit(db, user, "review.resolve", a.manuscript_id)
    db.commit()
    return svc.comment_out(db, c, anonymize=False)


class CompleteIn(BaseModel):
    recommendation: str
    summary_opinion: str = Field(min_length=1)


@router.post("/reviews/{aid}/complete")
def review_complete(aid: uuid.UUID, payload: CompleteIn, db: Session = Depends(get_db), user: User = Depends(reviewer_roles)):
    a = _my_assignment(db, user, aid)
    cfg = svc.get_settings(db)
    if payload.recommendation not in [o["key"] for o in cfg["decision_outcomes"]]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "알 수 없는 검토 의견 구분입니다")
    if a.status == "completed":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 완료된 검토입니다")
    if not a.conflict_checked:
        raise HTTPException(status.HTTP_409_CONFLICT, "이해상충 여부를 먼저 확인(신고)해야 검토를 완료할 수 있습니다")
    a.status, a.completed_at = "completed", svc.now()
    a.recommendation, a.summary_opinion = payload.recommendation, payload.summary_opinion
    _audit(db, user, "review.complete", a.manuscript_id, recommendation=payload.recommendation)
    db.commit()
    return _review_view(db, a)
