import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    ClassificationMethod,
    ClusterReviewStatus,
    DisputeAnalysisStatus,
    FieldCode,
    IssueMembershipType,
    TimelineEventType,
    VerificationStatus,
)


class IssueClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    field_code: FieldCode
    first_seen_at: datetime
    last_activity_at: datetime | None
    status: str
    review_status: ClusterReviewStatus
    created_by_method: ClassificationMethod | None
    summary: str | None
    document_count: int = 0


class IssueMemberDocumentOut(BaseModel):
    document_id: uuid.UUID
    title: str
    origin_url: str
    published_at: datetime | None
    membership_type: IssueMembershipType
    similarity_score: float | None
    judgment_reasoning: str | None


class IssueTimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    compared_to_document_id: uuid.UUID | None
    event_type: TimelineEventType
    event_date: datetime | None
    event_date_label: str | None
    description: str | None


class IssueDisputePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dispute_title: str
    claim_a_text: str
    claim_a_stakeholder: str | None
    claim_a_source_document_id: uuid.UUID | None
    claim_b_text: str
    claim_b_stakeholder: str | None
    claim_b_source_document_id: uuid.UUID | None
    common_ground: str | None
    differences: str | None
    unresolved_notes: str | None
    method: ClassificationMethod


class IssueAnalysisOut(BaseModel):
    """화면에서 '규칙 기반 자동분석'과 '연구원 확인 완료'를 구분해 보여줄 수 있도록
    저장된 세부 항목(JSON 포함)을 그대로 내려준다 — 요약 필드만 노출하면 핵심쟁점·국가비교·
    국내시사점 세부항목을 화면에 표시할 수 없어 Phase 2-4 지시사항을 충족하지 못한다."""

    model_config = ConfigDict(from_attributes=True)

    issue_cluster_id: uuid.UUID
    key_summary: str | None
    background_purpose: str | None
    policy_tech_change: str | None
    key_figures_json: str | None
    technical_issues_json: str | None
    policy_issues_json: str | None
    industry_concerns_json: str | None
    unconfirmed_points_json: str | None
    country_positions_json: str | None
    domestic_industry_relevance: str | None
    domestic_rnd_impact: str | None
    domestic_policy_considerations: str | None
    domestic_monitoring_points: str | None
    domestic_has_sufficient_basis: bool
    dispute_status: DisputeAnalysisStatus
    source_citations_json: str | None
    verification_status: VerificationStatus
    generated_by: ClassificationMethod


class IssueDetailOut(BaseModel):
    cluster: IssueClusterOut
    members: list[IssueMemberDocumentOut]
    timeline: list[IssueTimelineEventOut]
    analysis: IssueAnalysisOut | None
    disputes: list[IssueDisputePointOut]


class ClusterMergeIn(BaseModel):
    target_cluster_id: uuid.UUID
    reason: str | None = None


class ClusterSplitIn(BaseModel):
    document_id: uuid.UUID
    reason: str | None = None


class ScoringConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_impact_weight: float
    timeliness_weight: float
    domestic_relevance_weight: float
    novelty_weight: float
    analysis_depth_weight: float


class ScoringConfigUpdate(BaseModel):
    policy_impact_weight: float | None = None
    timeliness_weight: float | None = None
    domestic_relevance_weight: float | None = None
    novelty_weight: float | None = None
    analysis_depth_weight: float | None = None


class CandidateRecommendationScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    candidate_id: uuid.UUID
    issue_cluster_id: uuid.UUID | None
    policy_impact_score: float | None
    timeliness_score: float | None
    domestic_relevance_score: float | None
    novelty_score: float | None
    analysis_depth_score: float | None
    total_score: float | None
    method: ClassificationMethod
    scored_at: datetime
