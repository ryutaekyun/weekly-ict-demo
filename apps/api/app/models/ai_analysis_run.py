import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class AIAnalysisRun(Base, UUIDPKMixin, TimestampMixin):
    """AI(또는 규칙 기반) 분석 1회 호출 기록 — 보고서 집필·쟁점 분석 단계에서도 재사용할 수 있도록
    문서 분류/추출 서비스 전용이 아니라 범용 로그 테이블로 둔다."""

    __tablename__ = "ai_analysis_runs"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)  # classification|value_assessment|structured_extract
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)  # anthropic|openai|None(rule-based)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    analysis_version: Mapped[str] = mapped_column(String(20), nullable=False)  # 예: "rule-v1", "ai-v1"
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success|failed|skipped_no_api_key
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_char_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
