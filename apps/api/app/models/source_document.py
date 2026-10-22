import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import DocumentType, FieldCode, SourceDocumentStatus, SourceType


class SourceDocument(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "source_documents"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_runs.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # origin_url은 더 이상 DB 유니크 제약을 걸지 않는다 — 동일 URL이 내용 변경으로 재수집되면
    # (dedup 로직이 content_hash 비교로 구분해) previous_version_id를 단 새 행으로 쌓이기 때문이다.
    # "완전히 동일한 내용의 중복"은 애플리케이션 레벨에서 걸러 아예 새 행을 만들지 않는다.
    origin_url: Mapped[str] = mapped_column(String(1000), index=True, nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)  # 본문 PDF 등 첨부 URL
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[SourceDocumentStatus] = mapped_column(
        Enum(SourceDocumentStatus, native_enum=False), nullable=False
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_documents.id"), nullable=True
    )
    # duplicate_of_id(동일 내용·다른 출처/URL)와는 다른 개념 — 같은 origin_url의 개정판을 가리킨다.
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_documents.id"), nullable=True
    )

    language: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 예: ko, en, ja, zh
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    document_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType, native_enum=False), default=DocumentType.OTHER, nullable=False
    )
    # 문서의 '실제' 분야 — 출처의 고정 분야(Source.field_code)와 다를 수 있다.
    # 이번 단계에서는 수집 시점에 출처의 field_code를 그대로 넣어두고, 실제 자동분류는 Phase 2-2에서 구현한다.
    field_code: Mapped[FieldCode] = mapped_column(Enum(FieldCode, native_enum=False), nullable=False)
    collection_method: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False), nullable=False)
    is_peer_reviewed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # 논문 외 유형은 null
    requires_primary_source_check: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
