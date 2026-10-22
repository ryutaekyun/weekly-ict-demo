import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import ClassificationMethod, ClassificationRelevance, FieldCode


class DocumentClassification(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """문서별 '현재' 분류 상태 — Source.field_code(출처 고정 분야)와는 별도로 관리한다.

    SourceDocument.field_code는 Phase 2-1에서 수집 시점에 출처 분야를 그대로 복사해 둔 값으로,
    과거 호환을 위해 그대로 남겨두고 더 이상 "진짜 분야"로 취급하지 않는다. 이 테이블의
    primary_field_code가 Phase 2-2 이후의 공식 분야다.
    """

    __tablename__ = "document_classifications"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), unique=True, nullable=False
    )
    primary_field_code: Mapped[FieldCode | None] = mapped_column(
        Enum(FieldCode, native_enum=False), nullable=True
    )
    # JSON 배열(문자열) — 예: '["sec", "conv"]'. 주 분야와 중복되지 않는다.
    related_field_codes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance: Mapped[ClassificationRelevance] = mapped_column(
        Enum(ClassificationRelevance, native_enum=False),
        default=ClassificationRelevance.PENDING_REVIEW,
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0.0~1.0, 방식별로 의미가 다름을 reasoning에 명시
    method: Mapped[ClassificationMethod] = mapped_column(
        Enum(ClassificationMethod, native_enum=False), nullable=False
    )
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON 배열 — 규칙 기반일 때 실제로 매칭된 키워드(가중치 포함)를 그대로 남겨 재현 가능하게 한다.
    matched_keywords_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_researcher_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    classified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DocumentClassificationHistory(Base, UUIDPKMixin, TimestampMixin):
    """분류가 바뀔 때마다(자동분류 최초 실행 포함) 한 행씩 남기는 이력 — 연구원 수정 추적용."""

    __tablename__ = "document_classification_history"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )  # null이면 시스템(자동분류)이 변경한 것
    previous_primary_field_code: Mapped[FieldCode | None] = mapped_column(
        Enum(FieldCode, native_enum=False), nullable=True
    )
    new_primary_field_code: Mapped[FieldCode | None] = mapped_column(
        Enum(FieldCode, native_enum=False), nullable=True
    )
    previous_relevance: Mapped[ClassificationRelevance | None] = mapped_column(
        Enum(ClassificationRelevance, native_enum=False), nullable=True
    )
    new_relevance: Mapped[ClassificationRelevance] = mapped_column(
        Enum(ClassificationRelevance, native_enum=False), nullable=False
    )
    method: Mapped[ClassificationMethod] = mapped_column(
        Enum(ClassificationMethod, native_enum=False), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # 연구원이 수정 시 입력한 사유
