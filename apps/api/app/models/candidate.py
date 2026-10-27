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
    # 연구원이 근거 원문을 직접 추가·제외한 기록(이슈에 묶인 문서 외 추가 / 이슈 문서 중 제외) — JSON 문서 ID 목록
    evidence_extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_excluded_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # 검토 담당 연구원

    reviews: Mapped[list["CandidateReview"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", order_by="CandidateReview.created_at"
    )
