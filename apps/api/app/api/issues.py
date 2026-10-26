import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.enums import FieldCode, UserRole
from app.models.candidate import Candidate
from app.models.issue_analysis import IssueAnalysis
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.issue_dispute_point import IssueDisputePoint
from app.models.issue_timeline_event import IssueTimelineEvent
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.schemas.issue import (
    CandidateRecommendationScoreOut,
    ClusterMergeIn,
    ClusterSplitIn,
    IssueAnalysisOut,
    IssueClusterOut,
    IssueDetailOut,
    IssueDisputePointOut,
    IssueMemberDocumentOut,
    IssueTimelineEventOut,
    ScoringConfigOut,
    ScoringConfigUpdate,
)
from app.services.candidate_recommendation import get_or_create_scoring_config, run_candidate_recommendation
from app.services.issue_analysis import run_issue_analysis
from app.services.issue_clustering import manual_merge_clusters, manual_split_document
from app.services.issue_pipeline import run_clustering_for_document
from app.services.link_quality import classify_url

router = APIRouter(prefix="/issues", tags=["issues"])


def _get_cluster_or_404(db: Session, cluster_id: uuid.UUID) -> IssueCluster:
    cluster = db.get(IssueCluster, cluster_id)
    if cluster is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="이슈 클러스터를 찾을 수 없습니다")
    return cluster


@router.get("", response_model=list[IssueClusterOut])
def list_issues(
    field_code: FieldCode | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(IssueCluster)
    if field_code is not None:
        stmt = stmt.where(IssueCluster.field_code == field_code)
    if published_after is not None:
        stmt = stmt.where(IssueCluster.last_activity_at >= published_after)
    if published_before is not None:
        stmt = stmt.where(IssueCluster.last_activity_at <= published_before)
    clusters = db.scalars(stmt.order_by(IssueCluster.last_activity_at.desc())).all()

    results = []
    for c in clusters:
        count = db.scalar(
            select(func.count()).select_from(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == c.id)
        )
        data = IssueClusterOut.model_validate(c).model_dump()
        data["document_count"] = count or 0
        results.append(IssueClusterOut(**data))
    return results


@router.get("/{issue_id}", response_model=IssueDetailOut)
def get_issue_detail(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    cluster = _get_cluster_or_404(db, issue_id)
    members = db.query(IssueClusterDocument).filter(IssueClusterDocument.issue_cluster_id == issue_id).all()
    member_out = []
    for m in members:
        doc = db.get(SourceDocument, m.document_id)
        _link = classify_url(doc.origin_url)
        member_out.append(
            IssueMemberDocumentOut(
                document_id=doc.id, title=doc.title, origin_url=doc.origin_url, published_at=doc.published_at,
                membership_type=m.membership_type, similarity_score=m.similarity_score,
                judgment_reasoning=m.judgment_reasoning,
                link_state=_link["state"], link_blocked=_link["blocked"], link_note=_link["note"], is_pdf=_link["is_pdf"],
                source_org=(db.get(Source, doc.source_id).org_name if db.get(Source, doc.source_id) else None), country_code=doc.country_code,
            )
        )

    timeline = db.scalars(
        select(IssueTimelineEvent)
        .where(IssueTimelineEvent.issue_cluster_id == issue_id)
        .order_by(IssueTimelineEvent.event_date)
    ).all()
    analysis = db.query(IssueAnalysis).filter_by(issue_cluster_id=issue_id).one_or_none()
    disputes = db.query(IssueDisputePoint).filter(IssueDisputePoint.issue_cluster_id == issue_id).all()

    cluster_data = IssueClusterOut.model_validate(cluster).model_dump()
    cluster_data["document_count"] = len(member_out)

    return IssueDetailOut(
        cluster=IssueClusterOut(**cluster_data),
        members=member_out,
        timeline=[IssueTimelineEventOut.model_validate(t) for t in timeline],
        analysis=IssueAnalysisOut.model_validate(analysis) if analysis else None,
        disputes=[IssueDisputePointOut.model_validate(d) for d in disputes],
        candidates=[{"id": str(c.id), "title": c.title, "status": c.status.value}
                    for c in db.scalars(select(Candidate).where(Candidate.issue_cluster_id == issue_id)).all()],
    )


@router.post("/cluster/{document_id}", response_model=IssueClusterOut)
def trigger_clustering(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    document = db.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문서를 찾을 수 없습니다")
    cluster = run_clustering_for_document(db, document, actor_user_id=current_user.id)
    count = db.scalar(
        select(func.count()).select_from(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == cluster.id)
    )
    data = IssueClusterOut.model_validate(cluster).model_dump()
    data["document_count"] = count or 0
    return IssueClusterOut(**data)


@router.post("/{issue_id}/analyze", response_model=IssueAnalysisOut)
def trigger_analysis(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    cluster = _get_cluster_or_404(db, issue_id)
    analysis = run_issue_analysis(db, cluster, prefer_ai=True)
    db.commit()
    return IssueAnalysisOut.model_validate(analysis)


@router.post("/{issue_id}/recommend", response_model=CandidateRecommendationScoreOut | None)
def trigger_recommendation(
    issue_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    cluster = _get_cluster_or_404(db, issue_id)
    result = run_candidate_recommendation(db, cluster, created_by_user_id=current_user.id)
    db.commit()
    if result is None:
        return None
    _, score = result
    log_action(
        db, actor_user_id=current_user.id, action="issue.recommend", entity_type="issue_cluster", entity_id=cluster.id,
        detail={"total_score": score.total_score},
    )
    db.commit()
    return CandidateRecommendationScoreOut.model_validate(score)


@router.patch("/{issue_id}/merge", response_model=IssueClusterOut)
def merge_clusters(
    issue_id: uuid.UUID,
    payload: ClusterMergeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    _get_cluster_or_404(db, issue_id)
    _get_cluster_or_404(db, payload.target_cluster_id)
    target = manual_merge_clusters(
        db, source_cluster_id=issue_id, target_cluster_id=payload.target_cluster_id,
        user_id=current_user.id, reason=payload.reason,
    )
    log_action(
        db, actor_user_id=current_user.id, action="issue.merge", entity_type="issue_cluster", entity_id=issue_id,
        detail={"target_cluster_id": str(payload.target_cluster_id), "reason": payload.reason},
    )
    db.commit()
    count = db.scalar(
        select(func.count()).select_from(IssueClusterDocument).where(IssueClusterDocument.issue_cluster_id == target.id)
    )
    data = IssueClusterOut.model_validate(target).model_dump()
    data["document_count"] = count or 0
    return IssueClusterOut(**data)


@router.post("/split", response_model=IssueClusterOut)
def split_document(
    payload: ClusterSplitIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    new_cluster = manual_split_document(db, document_id=payload.document_id, user_id=current_user.id, reason=payload.reason)
    log_action(
        db, actor_user_id=current_user.id, action="issue.split", entity_type="source_document",
        entity_id=payload.document_id, detail={"new_cluster_id": str(new_cluster.id), "reason": payload.reason},
    )
    db.commit()
    data = IssueClusterOut.model_validate(new_cluster).model_dump()
    data["document_count"] = 1
    return IssueClusterOut(**data)


@router.get("/scoring/config", response_model=ScoringConfigOut)
def get_scoring_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return get_or_create_scoring_config(db)


@router.patch("/scoring/config", response_model=ScoringConfigOut)
def update_scoring_config(
    payload: ScoringConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    config = get_or_create_scoring_config(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(config, field, value)
    config.updated_by_user_id = current_user.id
    log_action(
        db, actor_user_id=current_user.id, action="scoring_config.update", entity_type="candidate_scoring_config",
        entity_id=config.id, detail=payload.model_dump(exclude_unset=True),
    )
    db.commit()
    db.refresh(config)
    return config
