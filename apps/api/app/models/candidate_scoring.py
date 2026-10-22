import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import ClassificationMethod

DEFAULT_WEIGHTS = {
    "policy_impact": 0.30,
    "timeliness": 0.20,
    "domestic_relevance": 0.20,
    "novelty": 0.15,
    "analysis_depth": 0.15,
}


class CandidateScoringConfig(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """후보주제 추천 점수 가중치 — 싱글턴 1행. 관리자가 PATCH로 수정한다."""

    __tablename__ = "candidate_scoring_config"

    policy_impact_weight: Mapped[float] = mapped_column(Float, default=DEFAULT_WEIGHTS["policy_impact"], nullable=False)
    timeliness_weight: Mapped[float] = mapped_column(Float, default=DEFAULT_WEIGHTS["timeliness"], nullable=False)
    domestic_relevance_weight: Mapped[float] = mapped_column(
        Float, default=DEFAULT_WEIGHTS["domestic_relevance"], nullable=False
    )
    novelty_weight: Mapped[float] = mapped_column(Float, default=DEFAULT_WEIGHTS["novelty"], nullable=False)
    analysis_depth_weight: Mapped[float] = mapped_column(Float, default=DEFAULT_WEIGHTS["analysis_depth"], nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class CandidateRecommendationScore(Base, UUIDPKMixin, TimestampMixin):
    """후보주제 1건에 대한 AI/규칙 기반 추천 점수 산출 근거."""

    __tablename__ = "candidate_recommendation_scores"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), unique=True, nullable=False)
    issue_cluster_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("issue_clusters.id"), nullable=True)

    # 0~100 원점수(가중치 적용 전). 근거 부족 시 null로 두고 reasoning에 "평가 보류" 명시.
    policy_impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeliness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    domestic_relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_depth_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    total_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weights_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)  # 산출 당시 가중치 스냅샷
    reasoning_json: Mapped[str] = mapped_column(Text, nullable=False)  # 기준별 근거/평가보류 사유
    duplicate_check_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 기발간 주제와의 중복 여부

    method: Mapped[ClassificationMethod] = mapped_column(Enum(ClassificationMethod, native_enum=False), nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
