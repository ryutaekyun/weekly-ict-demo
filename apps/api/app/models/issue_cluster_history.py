import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class IssueClusterMembershipHistory(Base, UUIDPKMixin, TimestampMixin):
    """클러스터 소속 변경 이력 — 자동 배정, 연구원의 병합·분리·복구를 전부 기록한다."""

    __tablename__ = "issue_cluster_membership_history"

    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    previous_issue_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("issue_clusters.id"), nullable=True
    )
    new_issue_cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("issue_clusters.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # assigned|merged|split|removed|restored
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
