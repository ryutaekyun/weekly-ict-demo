import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import ClassificationMethod, UsageValueRating


class DocumentValueAssessment(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """실무 활용가치 판정 — 우선검토/일반검토/관련성낮음/추가확인필요.

    시의성(최근 7/30/90일/과거)은 판정 시점이 아니라 "지금 보는 시점" 기준으로 늘 다시 계산해야
    하는 값이라 여기 저장하지 않는다(app.services.value_assessment.compute_recency_bucket 참고).
    """

    __tablename__ = "document_value_assessments"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), unique=True, nullable=False
    )
    rating: Mapped[UsageValueRating] = mapped_column(Enum(UsageValueRating, native_enum=False), nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)  # 원문에서 그대로 인용한 근거 문장
    method: Mapped[ClassificationMethod] = mapped_column(
        Enum(ClassificationMethod, native_enum=False), nullable=False
    )
    is_researcher_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # JSON 객체 — 6개 판정기준 각각의 충족 여부/메모(① 분야관련성 ~ ⑥ 출처신뢰성)
    criteria_json: Mapped[str | None] = mapped_column(Text, nullable=True)
