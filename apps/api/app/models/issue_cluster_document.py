import uuid

from sqlalchemy import Enum, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ClassificationMethod, IssueMembershipType


class IssueClusterDocument(Base, UUIDPKMixin, TimestampMixin):
    """이슈 클러스터 ↔ 문서 소속 관계. 한 문서는 한 클러스터에만 속한다(중복 소속 금지).

    "동일 문서 중복 수집"(SourceDocument.status=DUPLICATE)과는 다른 개념이다 — 여기서는
    서로 다른 출처가 같은 사건을 보도한 "동일 사건, 다른 문서"를 하나의 클러스터로 묶는다.
    """

    __tablename__ = "issue_cluster_documents"
    __table_args__ = (UniqueConstraint("document_id", name="uq_issue_cluster_documents_document_id"),)

    issue_cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issue_clusters.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    membership_type: Mapped[IssueMembershipType] = mapped_column(
        Enum(IssueMembershipType, native_enum=False), nullable=False
    )
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    judgment_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[ClassificationMethod] = mapped_column(Enum(ClassificationMethod, native_enum=False), nullable=False)
