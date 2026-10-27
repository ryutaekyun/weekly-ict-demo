import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
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

    error_code: Mapped[str | None] = mapped_column(String(30), nullable=True)  # auth_error|model_error|rate_limited|timeout|provider_5xx|bad_response|truncated|...
    provider_request_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 외부 제공자에게 요청을 실제로 보냈는지(비용 발생 가능)
    pricing_version: Mapped[str | None] = mapped_column(String(60), nullable=True)  # 비용 계산에 쓴 단가 기준(예: "anthropic/claude-sonnet-5-5 v1 2026-10-27")
    cancel_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 실제 공급자 응답 본문(공개 원문 분석 결과 JSON, 키·헤더 미포함) — 사후 대조·감사용
    source_changed_during_run: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIPriceSetting(Base, UUIDPKMixin, TimestampMixin):
    """관리자가 갱신하는 제공자·모델별 토큰 단가(USD/100만 토큰). 코드에 가격표를 박아 두지 않는다. 비용은 항상 '추정'이며 실제 청구액과 다를 수 있다."""

    __tablename__ = "ai_price_settings"

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)  # 정확한 모델 ID
    input_per_mtok: Mapped[float] = mapped_column(Float, nullable=False)
    output_per_mtok: Mapped[float] = mapped_column(Float, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)  # 요금 기준일
    source_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class AIInsertion(Base, UUIDPKMixin, TimestampMixin):
    """AI 문장이 원고에 삽입된 기록 — 삽입 시점의 원문 버전·발췌문과 AI 원문/연구원 최종 문장을 구분해 보존하고,
    원문이 바뀌면 재검토 필요를 판단하는 기준이 된다. 과거 승인본·출력본은 이 기록과 무관하게 보존된다."""

    __tablename__ = "ai_insertions"

    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_analyses.id"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_claims.id"), nullable=False)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id"), nullable=False, index=True)
    footnote_mark_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    inserted_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    ai_text: Mapped[str] = mapped_column(Text, nullable=False)  # AI가 만든 원래 문장
    final_text: Mapped[str] = mapped_column(Text, nullable=False)  # 연구원이 고쳐 실제 삽입한 문장
    edited_by_researcher: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quote_at_insert: Mapped[str | None] = mapped_column(Text, nullable=True)  # 삽입 시점의 근거 발췌문
    source_hash_at_insert: Mapped[str | None] = mapped_column(String(64), nullable=True)
    baseline_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 연구원이 마지막으로 확인한 원문 버전(삽입 시 = at_insert)
    position_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(12), default="active", nullable=False)  # active | undone | removed
    last_review_resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)  # updated | no_impact | needs_check | removed
    last_review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_review_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 확인한 원문 버전
    review_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 이전 검토 이력(append-only)


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


class AICallApproval(Base, UUIDPKMixin, TimestampMixin):
    """실제(비모의) 유료 AI 호출 1건에 대한 관리자 승인 — 대상(종류·ID)·모델·예산 상한을 지정하고 한 번 쓰면 소멸한다(자동 재시도·다음 문서 자동 분석 금지)."""

    __tablename__ = "ai_call_approvals"

    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    max_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)  # 이 호출의 예산 상한 — 예상 비용이 넘으면 호출 전에 차단
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    approved_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_analysis_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AIEvaluation(Base, UUIDPKMixin, TimestampMixin):
    """연구원의 AI 분석 품질 평가(7개 항목). 모의 공급자 결과와 실제 AI 결과는 같은 정확도 집계에 합산하지 않는다(is_mock로 구분)."""

    __tablename__ = "ai_evaluations"

    analysis_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_analyses.id"), nullable=False, index=True)
    evaluator_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_mock: Mapped[bool] = mapped_column(Boolean, nullable=False)
    scores_json: Mapped[str] = mapped_column(Text, nullable=False)  # {"c1_summary": "ok|partial|bad|na", ...}
    semantic_mismatch_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    insufficient_evidence_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wrong_source_cases: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_stats_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 평가 시점의 자동 검증 통계 스냅샷
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
