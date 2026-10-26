import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.audit_log import AuditLog
from app.models.candidate import Candidate
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.candidate_review import CandidateReview
from app.models.candidate_scoring import CandidateRecommendationScore
from app.models.enums import CandidateStatus, FieldCode, UserRole
from app.models.user import User
from app.services.link_quality import classify_url
from app.schemas.candidate import (
    CandidateCreate,
    CandidateDetailOut,
    CandidateOut,
    CandidateRecommendationScoreOut,
    CandidateReviewCreate,
    CandidateReviewOut,
    CandidateUpdate,
)

router = APIRouter(prefix="/candidates", tags=["candidates"])


def _plain(value):
    """감사 로그(JSON)에 넣을 수 있는 값으로 바꾼다."""
    if isinstance(value, uuid.UUID):
        return str(value)
    return getattr(value, "value", value) if value is not None else None

APPROVAL_GATED_STATUSES = {CandidateStatus.FINAL, CandidateStatus.REJECTED}


@router.get("", response_model=list[CandidateOut])
def list_candidates(
    field_code: FieldCode | None = None,
    status_filter: CandidateStatus | None = Query(default=None, alias="status"),
    q: str | None = None,
    assignee_user_id: uuid.UUID | None = None,
    mine: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Candidate)
    if mine:
        stmt = stmt.where(Candidate.assignee_user_id == current_user.id)
    if assignee_user_id is not None:
        stmt = stmt.where(Candidate.assignee_user_id == assignee_user_id)
    if field_code is not None:
        stmt = stmt.where(Candidate.field_code == field_code)
    if status_filter is not None:
        stmt = stmt.where(Candidate.status == status_filter)
    if q:
        stmt = stmt.where(Candidate.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Candidate.created_at.desc())
    return db.scalars(stmt).all()


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = payload.model_dump()
    if data.get("assignee_user_id") and db.get(User, data["assignee_user_id"]) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="담당자를 찾을 수 없습니다")
    if data.get("source_document_id") and not data.get("issue_cluster_id"):  # 근거 문서가 속한 핵심 이슈를 자동 연결(기존 관계 재사용)
        member = db.scalar(select(IssueClusterDocument).where(IssueClusterDocument.document_id == data["source_document_id"]))
        if member is not None:
            data["issue_cluster_id"] = member.issue_cluster_id
    candidate = Candidate(**data, created_by_user_id=current_user.id)
    db.add(candidate)
    db.flush()
    log_action(
        db,
        actor_user_id=current_user.id,
        action="candidate.create",
        entity_type="candidate",
        entity_id=candidate.id,
        detail={"title": candidate.title, "field_code": candidate.field_code.value},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


def _get_candidate_or_404(db: Session, candidate_id: uuid.UUID) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="후보주제를 찾을 수 없습니다")
    return candidate


def _related_documents(db: Session, candidate: Candidate) -> list[dict]:
    """후보주제의 근거 원문: 대표 근거 문서 + 같은 핵심 이슈의 수집 문서. 뉴스 카드와 같은 원문 링크 상태를 쓴다."""
    ids: list[uuid.UUID] = []
    if candidate.source_document_id:
        ids.append(candidate.source_document_id)
    if candidate.issue_cluster_id:
        for m in db.scalars(select(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == candidate.issue_cluster_id)).all():
            if m.document_id not in ids:
                ids.append(m.document_id)
    out = []
    for doc_id in ids:
        doc = db.get(SourceDocument, doc_id)
        if doc is None:
            continue
        link = classify_url(doc.origin_url)
        src = db.get(Source, doc.source_id)
        out.append({"document_id": str(doc.id), "title": doc.title, "origin_url": doc.origin_url, "org": src.org_name if src else None,
                    "country_code": doc.country_code, "published_at": doc.published_at.isoformat() if doc.published_at else None,
                    "link_state": link["state"], "link_blocked": link["blocked"], "link_note": link["note"], "is_pdf": link["is_pdf"],
                    "is_primary": doc.id == candidate.source_document_id})
    return out


def _history(db: Session, candidate: Candidate) -> list[dict]:
    rows = db.scalars(select(AuditLog).where(AuditLog.entity_type == "candidate", AuditLog.entity_id == candidate.id)
                      .order_by(AuditLog.created_at.desc()).limit(50)).all()
    out = []
    for r in rows:
        actor = db.get(User, r.actor_user_id) if r.actor_user_id else None
        try:
            detail = json.loads(r.detail_json) if r.detail_json else None
        except ValueError:
            detail = None
        out.append({"action": r.action, "actor": actor.display_name if actor else None, "at": r.created_at.isoformat(), "detail": detail})
    return out


@router.get("/{candidate_id}", response_model=CandidateDetailOut)
def get_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    score = db.query(CandidateRecommendationScore).filter_by(candidate_id=candidate_id).one_or_none()
    data = CandidateOut.model_validate(candidate).model_dump()
    data["reviews"] = [CandidateReviewOut.model_validate(r) for r in candidate.reviews]
    data["recommendation_score"] = CandidateRecommendationScoreOut.model_validate(score) if score else None
    assignee = db.get(User, candidate.assignee_user_id) if candidate.assignee_user_id else None
    data["assignee_name"] = assignee.display_name if assignee else None
    data["related_documents"] = _related_documents(db, candidate)
    data["history"] = _history(db, candidate)
    return CandidateDetailOut(**data)


@router.patch("/{candidate_id}", response_model=CandidateOut)
def update_candidate(
    candidate_id: uuid.UUID,
    payload: CandidateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("assignee_user_id") and db.get(User, data["assignee_user_id"]) is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="담당자를 찾을 수 없습니다")
    before = {k: getattr(candidate, k) for k in data}  # 수정 이력에 변경 전후를 남긴다

    if "status" in data and data["status"] in APPROVAL_GATED_STATUSES:
        if current_user.role not in (UserRole.APPROVER, UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="확정/반려 상태 변경은 최종 승인자만 할 수 있습니다",
            )

    for field, value in data.items():
        setattr(candidate, field, value)

    log_action(
        db,
        actor_user_id=current_user.id,
        action="candidate.update",
        entity_type="candidate",
        entity_id=candidate.id,
        detail={"changes": {k: {"from": _plain(before[k]), "to": _plain(v)} for k, v in data.items() if _plain(before[k]) != _plain(v)}},
    )
    db.commit()
    db.refresh(candidate)
    return candidate


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate(
    candidate_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)
    if current_user.role != UserRole.ADMIN and candidate.created_by_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="본인이 등록한 후보주제만 삭제할 수 있습니다")
    log_action(
        db,
        actor_user_id=current_user.id,
        action="candidate.delete",
        entity_type="candidate",
        entity_id=candidate.id,
        detail={"title": candidate.title},
    )
    db.delete(candidate)
    db.commit()


@router.post("/{candidate_id}/reviews", response_model=CandidateReviewOut, status_code=status.HTTP_201_CREATED)
def add_review(
    candidate_id: uuid.UUID,
    payload: CandidateReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidate = _get_candidate_or_404(db, candidate_id)

    if payload.is_final_approval:
        if current_user.role not in (UserRole.APPROVER, UserRole.ADMIN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="최종 승인 코멘트는 최종 승인자만 남길 수 있습니다",
            )
        if payload.decided_status is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="최종 승인에는 decided_status가 필요합니다")

    review = CandidateReview(
        candidate_id=candidate.id,
        reviewer_user_id=current_user.id,
        comment_text=payload.comment_text,
        is_final_approval=payload.is_final_approval,
        decided_status=payload.decided_status,
    )
    db.add(review)

    if payload.is_final_approval and payload.decided_status is not None:
        candidate.status = payload.decided_status

    log_action(
        db,
        actor_user_id=current_user.id,
        action="candidate.review.add" if not payload.is_final_approval else "candidate.approve",
        entity_type="candidate",
        entity_id=candidate.id,
        detail={"comment": payload.comment_text, "decided_status": payload.decided_status},
    )
    db.commit()
    db.refresh(review)
    return review
