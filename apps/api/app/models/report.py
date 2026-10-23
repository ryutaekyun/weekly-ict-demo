import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UpdatedAtMixin, UUIDPKMixin


class ReportTemplate(Base, UUIDPKMixin, TimestampMixin):
    """출력 서식(폰트·여백·머리글/바닥글·각주 표기 규칙 등). 수정 시 같은 name의 새 version 행을 만든다
    (이전 버전은 보존 — 과거 출력본이 어떤 서식으로 만들어졌는지 추적하기 위함).
    is_provisional=True는 공식 IITP 양식이 아닌 '임시 표준 템플릿'임을 뜻한다."""

    __tablename__ = "report_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_provisional: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Report(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """보고서 1건 = 회차(선택)에 속한 원고·요약문 묶음. report_type: general(일반호)/special(특집호)/summary(요약본)."""

    __tablename__ = "reports"

    edition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("editions.id"), nullable=True)
    report_type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_templates.id"), nullable=True)
    publish_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # draft → internal_approved → final. final은 '출력용 확정'이며 IITP 공식 확인과는 별개다.
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    finalize_exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    finalized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    iitp_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ReportItem(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """보고서의 한 구성요소. 원고 참조(manuscript_id) 또는 요약문(summary_text, 원고 문장에서 선택·편집)."""

    __tablename__ = "report_items"

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    part_key: Mapped[str | None] = mapped_column(String(40), nullable=True)  # key_issue/country_trend/field_brief/schedule/free
    heading: Mapped[str | None] = mapped_column(String(300), nullable=True)  # 특집호 등에서 연구원이 지정하는 소제목
    manuscript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscripts.id"), nullable=True)

    # 요약본 항목 — 연구원이 선택한 원고 문장 스냅샷과 편집된 요약문을 분리 저장한다(원본이 바뀌어도 덮어쓰지 않음)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReportExport(Base, UUIDPKMixin, TimestampMixin):
    """출력본(스냅샷) 1건. 어떤 원고 버전·템플릿 버전으로 만들었는지 고정하고, 파일 해시·크기를 남긴다."""

    __tablename__ = "report_exports"

    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id"), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)  # docx / pdf
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")  # running/success/failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("report_templates.id"), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 출력 시점 고정 입력(원고 본문·각주·버전)
    manuscript_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(600), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    footnote_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    table_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 출력 시점 발간 점검 결과
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 출력용 확정 후 생성한 출력본
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
