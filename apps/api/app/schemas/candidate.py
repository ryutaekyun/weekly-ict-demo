import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import CandidateStatus, ClassificationMethod, FieldCode


class CandidateCreate(BaseModel):
    field_code: FieldCode
    title: str
    summary: str | None = None
    source_document_id: uuid.UUID | None = None
    issue_cluster_id: uuid.UUID | None = None
    announced_date: date | None = None
    source_org: str | None = None
    recommended_reason: str | None = None
    assignee_user_id: uuid.UUID | None = None


class CandidateUpdate(BaseModel):
    field_code: FieldCode | None = None
    title: str | None = None
    summary: str | None = None
    announced_date: date | None = None
    source_org: str | None = None
    recommended_reason: str | None = None
    status: CandidateStatus | None = None
    assignee_user_id: uuid.UUID | None = None


class CandidateReviewCreate(BaseModel):
    comment_text: str
    is_final_approval: bool = False
    decided_status: CandidateStatus | None = None


class CandidateReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reviewer_user_id: uuid.UUID
    comment_text: str
    is_final_approval: bool
    decided_status: CandidateStatus | None
    created_at: datetime


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_code: FieldCode
    title: str
    summary: str | None
    issue_cluster_id: uuid.UUID | None = None
    source_document_id: uuid.UUID | None = None
    announced_date: date | None
    source_org: str | None
    recommended_reason: str | None
    status: CandidateStatus
    created_by_user_id: uuid.UUID
    assignee_user_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


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
    weights_snapshot_json: str
    reasoning_json: str
    duplicate_check_json: str | None
    method: ClassificationMethod
    scored_at: datetime


class CandidateDetailOut(CandidateOut):
    reviews: list[CandidateReviewOut] = []
    recommendation_score: CandidateRecommendationScoreOut | None = None
    assignee_name: str | None = None
    related_documents: list[dict] = []  # 근거 원문(핵심 이슈의 수집 문서) — 원문 링크 상태 포함
    excluded_documents: list[dict] = []  # 연구원이 근거에서 제외한 원문(복원 가능)
    issue_summary: dict | None = None  # 핵심 이슈·발표 시점·후속 동향·논쟁 가능성(규칙 기반 분석 결과)
    domestic_relevance_note: str | None = None
    history: list[dict] = []  # 수정 이력(감사 로그)
