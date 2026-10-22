import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import SourceDocumentStatus


class SourceDocument(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "source_documents"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False)
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("collection_runs.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    origin_url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[SourceDocumentStatus] = mapped_column(
        Enum(SourceDocumentStatus, native_enum=False), nullable=False
    )
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("source_documents.id"), nullable=True
    )
