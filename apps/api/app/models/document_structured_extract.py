import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import ClassificationMethod, VerificationStatus


class DocumentStructuredExtract(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """원문 기반 핵심 내용 구조화 — 보고서 집필에 바로 쓸 수 있는 형태로 분해한 결과.

    규칙 기반(AI 미설정) 모드에서는 원문에서 직접 패턴매칭으로 뽑을 수 있는 항목
    (핵심 수치/일정/관계기관)만 채우고, 해석이 필요한 항목(쟁점, 예상 영향)은 비워 둔다 —
    "원문에 없는 내용을 추정해 사실처럼 작성하지 않는다"는 원칙 때문이다.
    """

    __tablename__ = "document_structured_extracts"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id"), unique=True, nullable=False
    )
    key_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    background_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_tech_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_figures_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_dates_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    contested_points: Mapped[str | None] = mapped_column(Text, nullable=True)  # 원문에서 확인되는 경우에만
    expected_impact_facts: Mapped[str | None] = mapped_column(Text, nullable=True)  # 원문에 적힌 사실
    expected_impact_ai_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI의 해석(사실과 구분)
    open_questions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON 객체 — 각 항목명 -> 근거(원문 문단 설명/페이지/문장 인용)
    source_citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False
    )
    generated_by: Mapped[ClassificationMethod] = mapped_column(
        Enum(ClassificationMethod, native_enum=False), nullable=False
    )
