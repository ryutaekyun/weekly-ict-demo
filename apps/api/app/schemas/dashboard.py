import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import FieldCode


class FieldCountOut(BaseModel):
    field_code: FieldCode
    document_count: int


class RecentActivityItemOut(BaseModel):
    document_id: uuid.UUID
    title: str
    event: str  # "collected" | "classified" | "analyzed"
    occurred_at: datetime


class SourceStatusOut(BaseModel):
    source_id: uuid.UUID
    name: str
    org_name: str
    is_active: bool
    needs_review: bool
    last_run_status: str | None
    last_successful_collection_at: datetime | None
    consecutive_failures: int


class DashboardSummaryOut(BaseModel):
    """실제 DB 조회 결과만 담는다 — 프런트엔드에 숫자를 하드코딩하지 않기 위한 단일 출처.

    총 수집자료와 ICT 관련(분류=matched) 문서, 분류보류·관련성낮음 문서를 서로 혼동하지 않도록
    항목을 분리해서 내려준다(Phase 2-4 지시사항)."""

    total_documents: int
    matched_documents: int
    low_relevance_documents: int
    pending_review_documents: int
    unclassified_documents: int  # 아직 Phase 2-2 파이프라인을 거치지 않은 문서
    by_field: list[FieldCountOut]
    matched_without_field: int = 0  # 관련 자료이지만 주 분야가 지정되지 않은 건수(분야별 합계 + 이 값 = 관련 자료 수)
    issue_cluster_without_candidate: int = 0  # 후보주제가 없는 핵심 이슈(행정·공지성 등 사유는 이슈 화면에 표시)

    extraction_success: int
    extraction_summary_only: int
    extraction_partial: int
    extraction_failed: int
    extraction_not_attempted: int

    issue_cluster_total: int
    issue_cluster_confirmed: int
    issue_cluster_needs_review: int
    issue_cluster_multi_document: int

    candidate_total: int
    candidate_by_status: dict[str, int]

    domestic_relevance_assessed: int
    domestic_relevance_pending: int

    source_total: int
    source_active: int
    source_needs_review: int

    recent_activity: list[RecentActivityItemOut]
    generated_at: datetime
