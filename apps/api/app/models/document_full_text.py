import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ExtractionMethod, ExtractionStatus


class DocumentFullText(Base, UUIDPKMixin, TimestampMixin):
    """원문 전문 추출 결과 — 요약문(SourceDocument.raw_text)과는 별도로 저장한다.

    document_id는 unique=True로 두어 "현재" 추출 결과 1건만 가리키게 하고, 재추출로 내용이
    바뀌면 previous_extraction_id로 이전 레코드를 체인처럼 연결해 이력을 남긴다(완전히 지우지 않음).
    """

    __tablename__ = "document_full_texts"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), unique=True, nullable=False
    )
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, native_enum=False), nullable=False
    )
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        Enum(ExtractionMethod, native_enum=False), default=ExtractionMethod.NONE, nullable=False
    )
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 예: "본문 <article> 기준 14개 문단" / "PDF p.1-12(총 12p)" — 사람이 원문과 대조할 때 쓰는 위치 설명
    source_location: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_changed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    previous_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("document_full_texts.id"), nullable=True
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
