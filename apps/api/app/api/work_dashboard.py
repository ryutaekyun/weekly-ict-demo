"""로그인 직후 첫 화면 — 연구원 개인 업무 대시보드 집계. 모두 실제 DB 조회 결과이며, 테스트·시범 자료(제목 표지)는 제외한다."""
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.audit_log import AuditLog
from app.models.candidate import Candidate
from app.models.document_classification import DocumentClassification
from app.models.enums import CandidateStatus, ClassificationRelevance, ManuscriptStatus
from app.models.issue_cluster import IssueCluster, IssueClusterStatus
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.manuscript import Manuscript
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

TEST_MARKERS = ("E2E", "e2e-", "[시범]", "[합성", "3-6", "3-7", "3-8", "Synthetic", "CI Fixture")


def _not_test(col):
    return ~or_(*[col.contains(m) for m in TEST_MARKERS])


def _doc_row(db: Session, d: SourceDocument, field: str | None) -> dict:
    src = db.get(Source, d.source_id)
    return {"id": str(d.id), "title": d.title, "org": src.org_name if src else None, "country": d.country_code, "field": field,
            "published_at": d.published_at.isoformat() if d.published_at else None, "origin_url": d.origin_url}


@router.get("/work")
def work_dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    try:
        favs = json.loads(user.favorite_fields_json) if user.favorite_fields_json else []
    except ValueError:
        favs = []

    real_docs = select(SourceDocument).where(_not_test(SourceDocument.title))
    new_today = db.scalar(select(func.count()).select_from(real_docs.where(SourceDocument.collected_at >= since).subquery())) or 0
    total_docs = db.scalar(select(func.count()).select_from(real_docs.subquery())) or 0

    cand_open = (CandidateStatus.REC, CandidateStatus.REVIEW, CandidateStatus.RESEARCH)
    pending_candidates = db.scalar(select(func.count()).select_from(Candidate).where(Candidate.status.in_(cand_open), _not_test(Candidate.title))) or 0

    mine_active = (ManuscriptStatus.DRAFT, ManuscriptStatus.CHANGES_REQUESTED)
    my_ms = db.scalars(select(Manuscript).where(Manuscript.author_user_id == user.id, Manuscript.status.in_(mine_active), _not_test(Manuscript.title))
                       .order_by(Manuscript.updated_at.desc()).limit(6)).all()
    my_ms_count = db.scalar(select(func.count()).select_from(Manuscript).where(Manuscript.author_user_id == user.id, Manuscript.status.in_(mine_active), _not_test(Manuscript.title))) or 0

    bad_sources = db.scalars(select(Source).where(Source.is_active.is_(True), or_(Source.consecutive_failures > 0, Source.needs_review.is_(True)))
                             .order_by(Source.consecutive_failures.desc()).limit(5)).all()

    def with_field(stmt):
        return db.execute(stmt.add_columns(DocumentClassification.primary_field_code)
                          .outerjoin(DocumentClassification, DocumentClassification.document_id == SourceDocument.id)).all()

    recent = [_doc_row(db, d, f.value if f else None) for d, f in with_field(
        select(SourceDocument).where(_not_test(SourceDocument.title)).order_by(SourceDocument.collected_at.desc()).limit(8))]
    fav_docs = []
    if favs:
        rows = db.execute(select(SourceDocument, DocumentClassification.primary_field_code)
                          .join(DocumentClassification, DocumentClassification.document_id == SourceDocument.id)
                          .where(DocumentClassification.relevance == ClassificationRelevance.MATCHED, DocumentClassification.primary_field_code.in_(favs),
                                 _not_test(SourceDocument.title))
                          .order_by(SourceDocument.published_at.desc().nullslast()).limit(6)).all()
        fav_docs = [_doc_row(db, d, f.value if f else None) for d, f in rows]

    issues = []
    multi = select(IssueClusterDocument.issue_cluster_id).group_by(IssueClusterDocument.issue_cluster_id).having(func.count() > 1)
    for c in db.scalars(select(IssueCluster).where(IssueCluster.status == IssueClusterStatus.ACTIVE, IssueCluster.id.in_(multi), _not_test(IssueCluster.title))
                        .order_by(IssueCluster.last_activity_at.desc().nullslast()).limit(5)).all():
        n = db.scalar(select(func.count()).select_from(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == c.id)) or 0
        issues.append({"id": str(c.id), "title": c.title, "field": c.field_code.value, "document_count": n, "last_activity": c.last_activity_at.date().isoformat() if c.last_activity_at else None})

    from app.services.candidate_priority import priority_review
    pr = priority_review(db)
    priority = [{"id": i["candidate_id"], "title": i["title"], "field": i["field_code"], "score": i["priority_score"], "flags": i["flags"]} for i in pr["items"][:5]]

    my_cands = db.scalars(select(Candidate).where(Candidate.assignee_user_id == user.id, Candidate.status.in_(cand_open), _not_test(Candidate.title))
                          .order_by(Candidate.updated_at.desc()).limit(6)).all()
    review_requests = db.scalars(select(Manuscript).where(Manuscript.reviewer_user_id == user.id, Manuscript.status == ManuscriptStatus.REVIEW_REQUESTED,
                                                           _not_test(Manuscript.title)).order_by(Manuscript.updated_at.desc()).limit(6)).all()
    history = db.scalars(select(AuditLog).where(AuditLog.actor_user_id == user.id).order_by(AuditLog.created_at.desc()).limit(8)).all()

    return {
        "greeting_name": user.display_name, "favorite_fields": favs,
        "kpi": {"new_today": new_today, "total_docs": total_docs, "pending_candidates": pending_candidates, "my_manuscripts": my_ms_count, "source_errors": len(bad_sources)},
        "recent_docs": recent, "favorite_docs": fav_docs, "issues": issues, "priority": priority,
        "my_tasks": [{"kind": "candidate", "id": str(c.id), "title": c.title, "status": c.status.value} for c in my_cands]
                    + [{"kind": "manuscript", "id": str(m.id), "title": m.title, "status": m.status.value} for m in my_ms],
        "review_requests": [{"id": str(m.id), "title": m.title, "status": m.status.value} for m in review_requests],
        "source_errors": [{"id": str(s.id), "name": s.name, "failures": s.consecutive_failures, "needs_review": s.needs_review} for s in bad_sources],
        "history": [{"action": h.action, "entity_type": h.entity_type, "entity_id": str(h.entity_id), "at": h.created_at.isoformat()} for h in history],
    }
