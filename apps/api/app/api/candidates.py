import json
import uuid

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
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


def _id_list(raw: str | None) -> list[str]:
    try:
        v = json.loads(raw) if raw else []
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


def _related_documents(db: Session, candidate: Candidate, *, excluded: bool = False) -> list[dict]:
    """후보주제의 근거 원문: 대표 근거 문서 + 같은 핵심 이슈의 수집 문서. 뉴스 카드와 같은 원문 링크 상태를 쓴다."""
    ids: list[uuid.UUID] = []
    if candidate.source_document_id:
        ids.append(candidate.source_document_id)
    if candidate.issue_cluster_id:
        for m in db.scalars(select(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == candidate.issue_cluster_id)).all():
            if m.document_id not in ids:
                ids.append(m.document_id)
    for extra in _id_list(candidate.evidence_extra_json):  # 연구원이 직접 추가한 근거 원문
        try:
            u = uuid.UUID(extra)
        except ValueError:
            continue
        if u not in ids:
            ids.append(u)
    excluded_ids = set(_id_list(candidate.evidence_excluded_json))
    ids = [i for i in ids if (str(i) in excluded_ids) == excluded]
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
                    "is_primary": doc.id == candidate.source_document_id, "added_by_researcher": str(doc.id) in _id_list(candidate.evidence_extra_json)})
    return out


DISPUTE_LABELS = {"not_analyzed": "분석 전", "no_disputes_confirmed": "확인된 주요 의견 대립 없음", "disputes_found": "의견 대립 확인됨"}


def _issue_summary(db: Session, candidate: Candidate) -> dict | None:
    """후보주제가 속한 핵심 이슈의 규칙 기반 분석 요약 — 발표 시점·후속 동향·논쟁 가능성을 연구원이 한 화면에서 보게 한다."""
    if candidate.issue_cluster_id is None:
        return None
    from app.models.issue_analysis import IssueAnalysis
    from app.models.issue_cluster import IssueCluster
    from app.models.issue_dispute_point import IssueDisputePoint
    from app.models.issue_timeline_event import IssueTimelineEvent

    cluster = db.get(IssueCluster, candidate.issue_cluster_id)
    if cluster is None:
        return None
    analysis = db.scalar(select(IssueAnalysis).where(IssueAnalysis.issue_cluster_id == cluster.id))
    disputes = db.scalars(select(IssueDisputePoint).where(IssueDisputePoint.issue_cluster_id == cluster.id)).all()
    events = db.scalars(select(IssueTimelineEvent).where(IssueTimelineEvent.issue_cluster_id == cluster.id).order_by(IssueTimelineEvent.event_date)).all()
    dispute_status = analysis.dispute_status.value if analysis else "not_analyzed"
    timeline = []
    for e in events:
        doc = db.get(SourceDocument, e.document_id)
        timeline.append({"date": e.event_date.date().isoformat() if e.event_date else None, "type": e.event_type.value, "label": e.event_date_label,
                         "document_id": str(e.document_id), "title": doc.title if doc else None, "description": e.description})
    member_count = db.scalar(select(func.count()).select_from(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == cluster.id)) or 0
    return {
        "issue_id": str(cluster.id), "title": cluster.title, "review_status": cluster.review_status.value, "document_count": member_count,
        "key_summary": analysis.key_summary if analysis else None, "dispute_status": dispute_status, "dispute_label": DISPUTE_LABELS.get(dispute_status, dispute_status),
        "dispute_count": len(disputes),
        "dispute_note": ("서로 다른 문서에서 상반된 주장이 규칙으로 확인된 경우에만 '의견 대립'으로 표시합니다." if dispute_status == "disputes_found" else
                         "단일 문서이거나 상반된 주장이 확인되지 않아 논쟁으로 표시하지 않습니다(여러 기관이 논쟁 중인 것으로 간주하지 마세요)."),
        "timeline": timeline,
        "first_published": timeline[0]["date"] if timeline else None, "latest_activity": cluster.last_activity_at.date().isoformat() if cluster.last_activity_at else None,
        "followup_count": sum(1 for e in timeline if e["type"] not in ("new_issue",)),
        "needs_cluster_review": cluster.review_status.value == "needs_review",
    }


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
    data["excluded_documents"] = _related_documents(db, candidate, excluded=True)
    data["issue_summary"] = _issue_summary(db, candidate)
    data["domestic_relevance_note"] = ("국내 ICT 산업 관련성은 근거 자료가 확보된 경우에만 평가하며, 근거가 없으면 점수를 주지 않고 '평가 보류'로 표시합니다."
                                       if score is None or score.domestic_relevance_score is None else None)
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


class EvidenceAction(BaseModel):
    document_id: uuid.UUID
    action: str  # add | exclude | restore
    note: str | None = None


@router.post("/{candidate_id}/evidence")
def change_evidence(
    candidate_id: uuid.UUID,
    payload: EvidenceAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """근거 원문을 연구원이 직접 추가·제외·복원한다. 문서 자체나 이슈 묶음은 바꾸지 않고 이 후보주제의 근거 목록만 바꾸며 이력이 남는다."""
    candidate = _get_candidate_or_404(db, candidate_id)
    if db.get(SourceDocument, payload.document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="원문 문서를 찾을 수 없습니다")
    did = str(payload.document_id)
    extra, excluded = _id_list(candidate.evidence_extra_json), _id_list(candidate.evidence_excluded_json)
    in_current = {d["document_id"] for d in _related_documents(db, candidate)}
    if payload.action == "add":
        if did in in_current:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 근거 원문에 포함되어 있습니다")
        if did in excluded:
            excluded.remove(did)
        elif did not in extra:
            extra.append(did)
    elif payload.action == "exclude":
        if did not in in_current:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="현재 근거 원문에 없는 문서입니다")
        if candidate.source_document_id and str(candidate.source_document_id) == did:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="대표 근거 문서는 제외할 수 없습니다 — 먼저 다른 문서를 대표로 지정하세요")
        excluded.append(did)
    elif payload.action == "restore":
        if did not in excluded:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="제외된 문서가 아닙니다")
        excluded.remove(did)
    else:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="action은 add·exclude·restore 중 하나여야 합니다")
    candidate.evidence_extra_json, candidate.evidence_excluded_json = json.dumps(extra), json.dumps(excluded)
    log_action(db, actor_user_id=current_user.id, action=f"candidate.evidence.{payload.action}", entity_type="candidate", entity_id=candidate.id,
               detail={"document_id": did, "note": payload.note})
    db.commit()
    return {"related_documents": _related_documents(db, candidate), "excluded_documents": _related_documents(db, candidate, excluded=True)}
