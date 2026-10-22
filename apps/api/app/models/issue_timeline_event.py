import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ClassificationMethod, TimelineEventType


class IssueTimelineEvent(Base, UUIDPKMixin, TimestampMixin):
    """이슈 클러스터에 새 문서가 들어올 때마다 "무엇이 달라졌는가"를 한 행으로 남긴다.

    event_date_label로 발표일/시행일/의견수렴마감일/확정일을 구분해, 정책 생애주기
    (발표→의견수렴→확정→시행)를 시간순으로 재구성할 수 있게 한다.
    """

    __tablename__ = "issue_timeline_events"

    issue_cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issue_clusters.id"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("source_documents.id"), nullable=False)
    compared_to_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )  # 무엇과 비교해 이 판정을 내렸는지(없으면 "비교 자료 부족"의 근거)
    event_type: Mapped[TimelineEventType] = mapped_column(Enum(TimelineEventType, native_enum=False), nullable=False)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_date_label: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 발표일|시행일|의견수렴마감일|확정일 등
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[ClassificationMethod] = mapped_column(Enum(ClassificationMethod, native_enum=False), nullable=False)
