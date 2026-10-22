import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    ClassificationMethod,
    ClassificationRelevance,
    ExtractionMethod,
    ExtractionStatus,
    FieldCode,
    UsageValueRating,
    VerificationStatus,
)


class ClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    primary_field_code: FieldCode | None
    related_field_codes: list[FieldCode] = []
    relevance: ClassificationRelevance
    confidence: float | None
    method: ClassificationMethod
    reasoning: str | None
    is_researcher_overridden: bool
    classified_at: datetime


class ClassificationOverrideIn(BaseModel):
    primary_field_code: FieldCode | None = None
    related_field_codes: list[FieldCode] = []
    relevance: ClassificationRelevance
    reason: str | None = None


class FullTextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    extraction_status: ExtractionStatus
    extraction_method: ExtractionMethod
    char_count: int
    source_location: str | None
    content_changed: bool
    failure_reason: str | None
    extracted_at: datetime
    full_text: str | None = None  # 목록 조회에서는 생략하고, 상세 조회에서만 채운다


class ValueAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    rating: UsageValueRating
    reasoning: str | None
    evidence_quote: str | None
    method: ClassificationMethod
    is_researcher_overridden: bool
    recency_bucket: str | None = None  # 조회 시점마다 계산해서 채워 넣는다(저장값 아님)


class ValueAssessmentOverrideIn(BaseModel):
    rating: UsageValueRating
    reason: str | None = None


class StructuredExtractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: uuid.UUID
    key_content: str | None
    background_purpose: str | None
    policy_tech_change: str | None
    contested_points: str | None
    expected_impact_facts: str | None
    expected_impact_ai_analysis: str | None
    open_questions: str | None
    verification_status: VerificationStatus
    generated_by: ClassificationMethod


class AIAnalysisRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    task_type: str
    provider: str | None
    model: str | None
    analysis_version: str
    status: str
    error_message: str | None
    retry_count: int
    started_at: datetime
    finished_at: datetime | None


class DocumentAnalysisOut(BaseModel):
    document_id: uuid.UUID
    classification: ClassificationOut | None
    full_text: FullTextOut | None
    value_assessment: ValueAssessmentOut | None
    structured_extract: StructuredExtractOut | None
    ai_runs: list[AIAnalysisRunOut] = []
