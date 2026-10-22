import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import ClassificationMethod, DisputeAnalysisStatus, VerificationStatus


class IssueAnalysis(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """이슈 클러스터 단위의 핵심내용·쟁점·국가비교·국내시사점 — 클러스터당 1건.

    원문 사실과 AI 해석을 분리하는 Phase 2-2 원칙을 그대로 따른다: *_facts/*_json 성격의
    필드는 원문에서 확인된 내용만, industry_impact_ai_analysis처럼 '_ai_analysis'가 붙은
    필드만 AI의 해석을 담는다.
    """

    __tablename__ = "issue_analyses"

    issue_cluster_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("issue_clusters.id"), unique=True, nullable=False)

    # ① 핵심 이슈
    key_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    background_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_tech_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_figures_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ③ 핵심 쟁점(기술/정책/산업우려/이해관계자 차이/미확인사항) — 카테고리별 리스트를 JSON으로
    technical_issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_issues_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry_concerns_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    unconfirmed_points_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ④ 국가별·기관별 비교 — [{country_or_org, position_summary, source_document_id}]
    country_positions_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ⑤ 국내 산업적 시사점 — 근거 부족 시 has_sufficient_basis=False로 "추가 분석 필요" 표시
    domestic_industry_relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    domestic_rnd_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    domestic_policy_considerations: Mapped[str | None] = mapped_column(Text, nullable=True)
    domestic_monitoring_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    domestic_has_sufficient_basis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    dispute_status: Mapped[DisputeAnalysisStatus] = mapped_column(
        Enum(DisputeAnalysisStatus, native_enum=False), default=DisputeAnalysisStatus.NOT_ANALYZED, nullable=False
    )

    source_citations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False
    )
    generated_by: Mapped[ClassificationMethod] = mapped_column(Enum(ClassificationMethod, native_enum=False), nullable=False)
