"""문서 클러스터 배정 -> 타임라인 기록 -> (클러스터 단위) 이슈분석 -> 후보주제 추천 오케스트레이션."""

from sqlalchemy.orm import Session

from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source_document import SourceDocument
from app.services.candidate_recommendation import run_candidate_recommendation
from app.services.issue_analysis import run_issue_analysis
from app.services.issue_clustering import assign_document_to_cluster
from app.services.issue_timeline import record_timeline_for_new_membership


def run_clustering_for_document(db: Session, document: SourceDocument, *, actor_user_id=None) -> IssueCluster:
    existing_membership = (
        db.query(IssueClusterDocument).filter(IssueClusterDocument.document_id == document.id).one_or_none()
    )
    already_assigned = existing_membership is not None
    cluster = assign_document_to_cluster(db, document, actor_user_id=actor_user_id)
    if not already_assigned:
        membership = db.query(IssueClusterDocument).filter_by(document_id=document.id).one()
        record_timeline_for_new_membership(db, cluster.id, document, membership.membership_type)
    db.commit()
    return cluster


def run_analysis_and_recommendation_for_cluster(
    db: Session, cluster: IssueCluster, *, created_by_user_id, prefer_ai: bool = True
):
    run_issue_analysis(db, cluster, prefer_ai=prefer_ai)
    db.commit()
    result = run_candidate_recommendation(db, cluster, created_by_user_id=created_by_user_id)
    db.commit()
    return result
