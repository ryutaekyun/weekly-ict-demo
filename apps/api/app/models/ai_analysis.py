import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class AIAnalysis(Base, UUIDPKMixin, TimestampMixin):
    """연구원이 명시적으로 요청한 AI 분석 1건(문서·이슈·후보주제·원고 초안).

    기존 규칙 기반 분석 테이블(issue_analyses·document_structured_extracts 등)을 덮어쓰지 않고 별도로 보존한다.
    '분석 성공(status)'과 '사실 검증(verification_status)'은 서로 다른 축이다 — AI 호출이 성공해도 근거 확인이 끝나기 전에는 검증 완료가 아니다.
    """

    __tablename__ = "ai_analyses"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # document | issue | candidate | outline | draft
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # document | issue | candidate
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    requested_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    status: Mapped[str] = mapped_column(String(24), nullable=False)  # running | completed | failed | cancelled | insufficient_evidence
    # ai_unverified | insufficient(근거 부족) | mismatch(근거 불일치) | researcher_verified
    verification_status: Mapped[str] = mapped_column(String(24), default="ai_unverified", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 모의 응답(개발·테스트 전용)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)

    request_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # 같은 대상·같은 원문 버전의 중복 요청 식별
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)  # 분석에 쓴 원문 버전의 해시
    input_documents_json: Mapped[str] = mapped_column(Text, nullable=False)  # [{id,title,url,content_hash,chars,published,truncated}]
    input_chars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 공급자가 보고한 실제값(없으면 0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    est_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    actual_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # {sections:[{key,title,claim_ids}], notes:[], hold_reason}
    notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 경고(원문 내 명령문 감지, 일부만 분석 등)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reused_from_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    linked_candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    public_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    public_approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIClaim(Base, UUIDPKMixin, TimestampMixin):
    """AI가 만든 문장 1건과 그 근거. 문서 ID·URL·위치는 서버가 채우며 AI가 쓴 값은 신뢰하지 않는다."""

    __tablename__ = "ai_claims"

    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_analyses.id"), nullable=False, index=True)
    section_key: Mapped[str] = mapped_column(String(40), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    claim_type: Mapped[str] = mapped_column(String(16), nullable=False)  # fact(원문 사실) | interpretation(AI 해석) | gap(확인 필요 사항)
    # [{document_id,url,title,quote,found,location,note}] — url은 source_documents.origin_url, 위치는 서버가 원문에서 계산
    evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    # found(근거 확인) | not_found(원문에 없음·검증 실패) | value_mismatch(근거 불일치) | no_evidence(근거 없음·확인 필요) | interpretation | gap
    evidence_status: Mapped[str] = mapped_column(String(16), nullable=False)
    check_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    researcher_status: Mapped[str] = mapped_column(String(12), default="unverified", nullable=False)  # unverified | verified | rejected
    researcher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inserted_manuscript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscripts.id"), nullable=True)
