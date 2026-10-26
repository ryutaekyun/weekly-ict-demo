"""주간기술동향지(전문가 기고문 편집·발간) 도메인 모델 — Phase 3-4.

주간 AI·ICT 동향보고서(연구원이 직접 집필)와 달리, 외부 전문가에게 원고를 의뢰·접수하고 검토·저자 수정·심의를 거쳐
게재 원고를 확정한 뒤 발간본을 만드는 편집 업무를 다룬다. 상태 값은 문자열이며 허용 값과 전이는 journal_service가 강제한다.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UpdatedAtMixin, UUIDPKMixin


class JournalSetting(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """관리자 설정(일정 기준·휴일·업로드 제한·형식 점검 기준·제출서류·심의 결과 구분). 값은 JSON."""

    __tablename__ = "tj_settings"

    key: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class JournalIssue(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "tj_issues"
    __table_args__ = (UniqueConstraint("year", "issue_no", name="uq_tj_issue_year_no"),)

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_no: Mapped[int] = mapped_column(Integer, nullable=False)
    publish_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # 관리자가 입력 — 자동 확정하지 않는다
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planning")
    tech_field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    editor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    iitp_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    iitp_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    iitp_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    iitp_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)  # 실제 발간 기록일(내부 기록)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class JournalScheduleStep(Base, UUIDPKMixin, TimestampMixin):
    """회차별 편집 일정 단계. 마감일(due_date)과 실제 완료일(completed_at)을 구분하며, 기한이 지나도 자동 완료하지 않는다."""

    __tablename__ = "tj_schedule_steps"

    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_issues.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_key: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    offset_days: Mapped[int] = mapped_column(Integer, nullable=False)  # 발간일 기준 D-n (마감)
    window_start_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # D-60~50처럼 기간이 있는 단계의 시작
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    window_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class JournalExpert(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """외부 전문가(집필진) — 개인정보를 포함하므로 편집 담당자 이상만 조회한다."""

    __tablename__ = "tj_experts"

    expert_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(200), nullable=True)
    position_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fields_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # ICT 9대 분야·세부 기술 분야(복수)
    research_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    consent_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")  # none / agreed / withdrawn
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consent_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    anonymized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # 포털 계정(선택)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class JournalCommission(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """원고 의뢰(집필 의뢰서). 의뢰서·안내 메일은 작성·미리보기·임시저장만 하며 실제 외부 발송은 하지 않는다."""

    __tablename__ = "tj_commissions"

    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_issues.id"), nullable=False)
    expert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_experts.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    outline: Mapped[str | None] = mapped_column(Text, nullable=True)
    length_spec: Mapped[str | None] = mapped_column(String(200), nullable=True)
    format_spec: Mapped[str | None] = mapped_column(String(300), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    delivery_method: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact_info: Mapped[str | None] = mapped_column(String(300), nullable=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)  # AI 추천 주제 ≠ IITP 확정 주제
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    mail_subject: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mail_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    mail_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none")  # none / draft / pending_send (sent 없음)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class JournalCommissionEvent(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tj_commission_events"

    commission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_commissions.id"), nullable=False)
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class JournalManuscript(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "tj_manuscripts"

    commission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_commissions.id"), unique=True, nullable=False)
    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_issues.id"), nullable=False)
    expert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_experts.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    authors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # [{name, affiliation, corresponding}]
    references_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="received")
    format_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_checked")  # 형식 검토(not_checked/needs_fix/ok)
    content_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # 내용 검토(pending/in_review/done)
    copyright_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 저자의 저작권·이용 동의 확인
    third_party_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 제3자 이미지·자료 사용 권한 기록
    version_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    proof_version_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    proof_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    proof_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JournalVersion(Base, UUIDPKMixin, TimestampMixin):
    """제출·수정·교정 시점마다 독립된 버전(원본 파일 보존, 덮어쓰기 없음)."""

    __tablename__ = "tj_versions"
    __table_args__ = (UniqueConstraint("manuscript_id", "version_no", name="uq_tj_version_no"),)

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # submission / revision / proofread
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(600), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)  # 저자 제출 메모·변경 요약
    scan_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 보안 검사 결과
    extract_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 추출 통계(문단·단어·표·그림 수, 추출 성공 여부)
    format_check_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    proof_checklist_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 교정본 점검표
    snapshot_title: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 제출 시점의 제목(메타데이터 변경 이력 보존)
    snapshot_authors_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class JournalAttachment(Base, UUIDPKMixin, TimestampMixin):
    """제출서류(확인서 등)·표·그림 첨부."""

    __tablename__ = "tj_attachments"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tj_versions.id"), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(60), nullable=False)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(600), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class JournalAssignment(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """검토자·심의위원 배정(회차별 1차/2차)."""

    __tablename__ = "tj_assignments"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    role_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="reviewer")  # reviewer / committee
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(14), nullable=False, default="assigned")  # assigned / in_progress / completed
    conflict_declared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 이해상충 있음
    conflict_checked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 이해상충 여부 확인함
    conflict_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 검토자 의견(결정 아님)
    summary_opinion: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class JournalComment(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """검토 의견(문서 전체·문단·표·그림에 연결) — 저자 답변과 대응 관계를 저장한다."""

    __tablename__ = "tj_comments"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tj_versions.id"), nullable=True)  # 의견을 단 버전
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tj_assignments.id"), nullable=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(12), nullable=False, default="review")  # review / format / deliberation
    scope: Mapped[str] = mapped_column(String(12), nullable=False, default="doc")  # doc / paragraph / table / figure
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    requires_revision: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")  # open / answered / resolved
    author_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    replied_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tj_versions.id"), nullable=True)  # 답변과 함께 제출한 수정본
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JournalDecision(Base, UUIDPKMixin, TimestampMixin):
    """심의 결정(실제 심의 담당자가 확정 — 자동 점수로 정하지 않는다)."""

    __tablename__ = "tj_decisions"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tj_versions.id"), nullable=True)
    round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 게재 확정·보류·반려 결정


class JournalPlagiarism(Base, UUIDPKMixin, TimestampMixin):
    """표절검사 결과 파일 — 외부 서비스 연동이 없으므로 결과 파일을 올리고 담당자가 확인한 기록만 남긴다."""

    __tablename__ = "tj_plagiarism"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tj_versions.id"), nullable=True)
    service_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(600), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    similarity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)  # 담당자가 결과 파일을 보고 입력한 값
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="uploaded")  # uploaded / confirmed
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JournalIssueItem(Base, UUIDPKMixin, TimestampMixin):
    """회차에 배치된 게재 원고(게재 확정된 원고의 특정 버전)."""

    __tablename__ = "tj_issue_items"
    __table_args__ = (UniqueConstraint("issue_id", "manuscript_id", name="uq_tj_issue_item"),)

    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_issues.id"), nullable=False)
    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_manuscripts.id"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_versions.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class JournalExport(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "tj_exports"

    issue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tj_issues.id"), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    items_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 출력에 쓴 원고·버전·해시 스냅샷
    validation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    issue_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
