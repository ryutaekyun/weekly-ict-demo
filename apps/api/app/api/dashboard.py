from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.candidate import Candidate
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.enums import ClassificationRelevance, ExtractionStatus
from app.models.issue_analysis import IssueAnalysis
from app.models.issue_cluster import IssueCluster, IssueClusterStatus
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.schemas.dashboard import DashboardSummaryOut, FieldCountOut, RecentActivityItemOut, SourceStatusOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """대시보드에 필요한 모든 집계를 실시간 DB 조회로 계산한다 — 프런트엔드 하드코딩 금지
    (Phase 2-4 지시사항). 재처리·재분석 후 바로 바뀌는 수치여야 한다."""

    total_documents = db.scalar(select(func.count()).select_from(SourceDocument)) or 0

    relevance_counts: dict[ClassificationRelevance, int] = dict(
        db.execute(
            select(DocumentClassification.relevance, func.count()).group_by(DocumentClassification.relevance)
        ).all()
    )
    matched = relevance_counts.get(ClassificationRelevance.MATCHED, 0)
    low_relevance = relevance_counts.get(ClassificationRelevance.LOW_RELEVANCE, 0)
    pending_review = relevance_counts.get(ClassificationRelevance.PENDING_REVIEW, 0)
    classified_total = db.scalar(select(func.count()).select_from(DocumentClassification)) or 0
    unclassified = total_documents - classified_total

    by_field_rows = db.execute(
        select(DocumentClassification.primary_field_code, func.count())
        .where(DocumentClassification.relevance == ClassificationRelevance.MATCHED)
        .where(DocumentClassification.primary_field_code.is_not(None))
        .group_by(DocumentClassification.primary_field_code)
    ).all()
    by_field = [FieldCountOut(field_code=fc, document_count=cnt) for fc, cnt in by_field_rows]

    extraction_counts: dict[ExtractionStatus, int] = dict(
        db.execute(
            select(DocumentFullText.extraction_status, func.count()).group_by(DocumentFullText.extraction_status)
        ).all()
    )

    active_clusters = select(IssueCluster).where(IssueCluster.status == IssueClusterStatus.ACTIVE).subquery()
    issue_cluster_total = db.scalar(select(func.count()).select_from(active_clusters)) or 0
    issue_review_rows = dict(
        db.execute(
            select(IssueCluster.review_status, func.count())
            .where(IssueCluster.status == IssueClusterStatus.ACTIVE)
            .group_by(IssueCluster.review_status)
        ).all()
    )
    issue_cluster_confirmed = sum(v for k, v in issue_review_rows.items() if k.value == "confirmed")
    issue_cluster_needs_review = sum(v for k, v in issue_review_rows.items() if k.value == "needs_review")

    multi_doc_cluster_ids = db.execute(
        select(IssueClusterDocument.issue_cluster_id)
        .group_by(IssueClusterDocument.issue_cluster_id)
        .having(func.count() > 1)
    ).all()
    issue_cluster_multi_document = len(multi_doc_cluster_ids)

    candidate_total = db.scalar(select(func.count()).select_from(Candidate)) or 0
    candidate_status_rows = db.execute(select(Candidate.status, func.count()).group_by(Candidate.status)).all()
    candidate_by_status = {status.value: cnt for status, cnt in candidate_status_rows}

    domestic_sufficient = db.scalar(
        select(func.count()).select_from(IssueAnalysis).where(IssueAnalysis.domestic_has_sufficient_basis.is_(True))
    ) or 0
    domestic_total = db.scalar(select(func.count()).select_from(IssueAnalysis)) or 0
    domestic_pending = domestic_total - domestic_sufficient

    source_total = db.scalar(select(func.count()).select_from(Source)) or 0
    source_active = db.scalar(select(func.count()).select_from(Source).where(Source.is_active.is_(True))) or 0
    source_needs_review = db.scalar(select(func.count()).select_from(Source).where(Source.needs_review.is_(True))) or 0

    recent_docs = db.execute(
        select(SourceDocument.id, SourceDocument.title, SourceDocument.collected_at)
        .order_by(SourceDocument.collected_at.desc())
        .limit(10)
    ).all()
    recent_activity = [
        RecentActivityItemOut(document_id=doc_id, title=title, event="collected", occurred_at=collected_at)
        for doc_id, title, collected_at in recent_docs
    ]

    return DashboardSummaryOut(
        total_documents=total_documents,
        matched_documents=matched,
        low_relevance_documents=low_relevance,
        pending_review_documents=pending_review,
        unclassified_documents=max(unclassified, 0),
        by_field=by_field,
        extraction_success=extraction_counts.get(ExtractionStatus.SUCCESS, 0),
        extraction_summary_only=extraction_counts.get(ExtractionStatus.SUMMARY_ONLY, 0),
        extraction_partial=extraction_counts.get(ExtractionStatus.PARTIAL, 0),
        extraction_failed=extraction_counts.get(ExtractionStatus.FAILED, 0),
        extraction_not_attempted=extraction_counts.get(ExtractionStatus.NOT_ATTEMPTED, 0),
        issue_cluster_total=issue_cluster_total,
        issue_cluster_confirmed=issue_cluster_confirmed,
        issue_cluster_needs_review=issue_cluster_needs_review,
        issue_cluster_multi_document=issue_cluster_multi_document,
        candidate_total=candidate_total,
        candidate_by_status=candidate_by_status,
        domestic_relevance_assessed=domestic_sufficient,
        domestic_relevance_pending=domestic_pending,
        source_total=source_total,
        source_active=source_active,
        source_needs_review=source_needs_review,
        recent_activity=recent_activity,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/sources-status", response_model=list[SourceStatusOut])
def get_sources_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """출처별 최근 수집 성공/실패 현황 — 출처·수집 관리 화면과 대시보드 카드에서 함께 쓴다."""
    from app.models.collection_run import CollectionRun

    sources = db.scalars(select(Source).order_by(Source.field_code)).all()
    results = []
    for s in sources:
        last_run = db.scalar(
            select(CollectionRun).where(CollectionRun.source_id == s.id).order_by(CollectionRun.started_at.desc()).limit(1)
        )
        results.append(
            SourceStatusOut(
                source_id=s.id,
                name=s.name,
                org_name=s.org_name,
                is_active=s.is_active,
                needs_review=s.needs_review,
                last_run_status=last_run.status.value if last_run else None,
                last_successful_collection_at=s.last_successful_collection_at,
                consecutive_failures=s.consecutive_failures,
            )
        )
    return results
