import uuid
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import CandidateStatus, FieldCode


class Candidate(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "candidates"

    issue_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("issue_clusters.id"), nullable=True
    )
    field_code: Mapped[FieldCode] = mapped_column(Enum(FieldCode, native_enum=False), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )
    announced_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_org: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recommended_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CandidateStatus] = mapped_column(
        Enum(CandidateStatus, native_enum=False), default=CandidateStatus.REC, nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    reviews: Mapped[list["CandidateReview"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateReview.created_at"
    )
