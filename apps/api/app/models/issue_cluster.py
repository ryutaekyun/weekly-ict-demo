import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import FieldCode


class IssueClusterStatus:
    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


class IssueCluster(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "issue_clusters"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    field_code: Mapped[FieldCode] = mapped_column(Enum(FieldCode, native_enum=False), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    representative_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default=IssueClusterStatus.ACTIVE, nullable=False)
