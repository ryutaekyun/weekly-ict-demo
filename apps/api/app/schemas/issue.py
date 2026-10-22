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
    claim_a_source_document_id: uuid.UUID | None
    claim_b_text: str
    claim_b_source_document_id: uuid.UUID | None
    common_ground: str | None
    differences: str | None
    unresolved_notes: str | None


class IssueAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    issue_cluster_id: uuid.UUID
    key_summary: str | None
    background_purpose: str | None
    policy_tech_change: str | None
    domestic_industry_relevance: str | None
    domestic_has_sufficient_basis: bool
    dispute_status: DisputeAnalysisStatus
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
