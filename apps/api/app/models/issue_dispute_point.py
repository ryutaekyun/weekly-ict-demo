import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ClassificationMethod


class IssueDisputePoint(Base, UUIDPKMixin, TimestampMixin):
    """이슈 클러스터 내 상반된 주장 1건. 논쟁이 없으면 행을 만들지 않고
    IssueAnalysis.dispute_status=NO_DISPUTES_CONFIRMED으로만 표시한다."""

    __tablename__ = "issue_dispute_points"

    issue_cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issue_clusters.id"), nullable=False)
    dispute_title: Mapped[str] = mapped_column(Text, nullable=False)
    claim_a_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_a_stakeholder: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_a_source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )
    claim_b_text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_b_stakeholder: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_b_source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )
    common_ground: Mapped[str | None] = mapped_column(Text, nullable=True)
    differences: Mapped[str | None] = mapped_column(Text, nullable=True)
    unresolved_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[ClassificationMethod] = mapped_column(Enum(ClassificationMethod, native_enum=False), nullable=False)
