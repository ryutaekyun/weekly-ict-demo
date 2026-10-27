import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    ClassificationMethod,
    ClassificationRelevance,
    DocumentType,
    ExtractionMethod,
    ExtractionStatus,
    FieldCode,
    SourceDocumentStatus,
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


class DocumentListItemOut(BaseModel):
    """목록·상세 화면 공용 — 출처 고정 분야가 아니라 document_classifications.primary_field_code를
    분야 판정 기준으로 쓴다(Phase 2-4 지시사항)."""

    id: uuid.UUID
    title: str
    origin_url: str
    attachment_url: str | None
    source_id: uuid.UUID
    source_name: str
    source_org_name: str
    country_code: str | None
    published_at: datetime | None
    collected_at: datetime
    document_type: DocumentType
    status: SourceDocumentStatus
    primary_field_code: FieldCode | None
    relevance: ClassificationRelevance | None
    classification_method: ClassificationMethod | None
    value_rating: UsageValueRating | None
    extraction_status: ExtractionStatus | None
    issue_cluster_id: uuid.UUID | None
    # 원문 링크 상태(형태 분류): document / homepage / search / invalid / missing — blocked면 원문 열기를 막고 사유를 보여준다
    link_state: str = "document"
    link_blocked: bool = False
    link_note: str | None = None
    is_pdf: bool = False
    # Phase 4-2: 원문 언어·버전(번역·재검토 연계 준비). 번역 상태는 번역 엔진이 연결되는 4-3 단계에서 채운다.
    language: str | None = None
    version_no: int = 1
    is_latest: bool = True
    external_id: str | None = None
    translation_status: str = "not_available"  # 번역 엔진 연결 전에는 'not_available'


class DocumentListOut(BaseModel):
    items: list[DocumentListItemOut]
    total: int
    page: int
    page_size: int
