import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UpdatedAtMixin, UUIDPKMixin


class CardNewsTemplate(Base, UUIDPKMixin, TimestampMixin):
    """카드뉴스 디자인 템플릿(색상·글꼴·기본 크기·여백). 수정은 같은 template_key의 새 version 행을 만든다.
    레이아웃(배치 규칙)은 코드(card_news_scene)에 있고, 여기에는 관리자가 바꿀 수 있는 설정값만 저장한다."""

    __tablename__ = "card_news_templates"

    template_key: Mapped[str] = mapped_column(String(10), nullable=False)  # A/B/C/D
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class CardNews(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """카드뉴스 1건(여러 장의 카드). 크기(cm)는 IITP 공식 규격이 아닌 작업용 기본값(7 × 15.62)이며 건별로 바꿀 수 있다."""

    __tablename__ = "card_news"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    template_key: Mapped[str] = mapped_column(String(10), nullable=False)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("card_news_templates.id"), nullable=True)
    width_cm: Mapped[float] = mapped_column(Float, nullable=False, default=7.0)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False, default=15.62)

    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")  # report/summary/manual
    source_report_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reports.id"), nullable=True)
    source_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 생성 시점의 원고별 lock_version

    # draft → review_requested → changes_requested → approved(내부 확정). IITP 공식 확인은 별도 플래그.
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    approve_exception_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    iitp_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    iitp_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_pilot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 시범 카드뉴스
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 합성 테스트 데이터 포함
    parent_card_news_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("card_news.id"), nullable=True)

    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class CardNewsCard(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "card_news_cards"

    card_news_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news.id"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # cover / body / closing
    bg_color: Mapped[str | None] = mapped_column(String(9), nullable=True)  # 카드별 배경색 덮어쓰기(없으면 템플릿 기본)


class CardNewsElement(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """카드 안의 편집 요소(텍스트·선택값·차트 데이터). key는 템플릿 스키마의 요소 식별자.
    style_json: size/color/bold/align 덮어쓰기, box: x/y/w/h(cm) 덮어쓰기."""

    __tablename__ = "card_news_elements"

    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news_cards.id"), nullable=False)
    key: Mapped[str] = mapped_column(String(60), nullable=False)
    element_type: Mapped[str] = mapped_column(String(10), nullable=False, default="text")  # text / choice / chart
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 차트 데이터 등 구조화 값
    style_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    box_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 보고서/요약본에서 가져온 원문 문장(추적용) — 이후 원고가 바뀌었는지 판정하는 기준
    source_manuscript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscripts.id"), nullable=True)
    source_sentence: Mapped[str | None] = mapped_column(Text, nullable=True)


class CardNewsEvidence(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """카드 요소 ↔ 원문 근거 연결 1건. 카드뉴스에서의 검증은 원고 각주 상태와 별개로 연구원이 명시적으로 해야 하며,
    검증 당시의 요소 텍스트 해시를 저장해 이후 내용이 수정되면 '재검토 필요'가 되게 한다."""

    __tablename__ = "card_news_evidence"

    card_news_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news.id"), nullable=False)
    card_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news_cards.id"), nullable=False)
    element_key: Mapped[str] = mapped_column(String(60), nullable=False)
    source_manuscript_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscripts.id"), nullable=True)
    source_footnote_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscript_footnotes.id"), nullable=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_org: Mapped[str | None] = mapped_column(String(200), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_footnote_status: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 원고 각주의 당시 상태(참고용)
    source_lock_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_verified")
    verified_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class CardNewsVersion(Base, UUIDPKMixin, TimestampMixin):
    """카드 구성·텍스트·디자인 전체 스냅샷. 자동저장마다 쌓지 않고 주요 버전·일정 간격 스냅샷만 남긴다."""

    __tablename__ = "card_news_versions"

    card_news_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class CardNewsReview(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "card_news_reviews"

    card_news_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news.id"), nullable=False)
    card_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("card_news_cards.id"), nullable=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="open")  # open / resolved
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CardNewsExport(Base, UUIDPKMixin, TimestampMixin):
    """출력본 1건(PPTX 또는 PNG 묶음). 출력 시점의 카드 내용·템플릿 버전을 snapshot_json으로 고정한다."""

    __tablename__ = "card_news_exports"

    card_news_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("card_news.id"), nullable=False)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)  # pptx / png
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 출력 당시 card_news.lock_version
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("card_news_templates.id"), nullable=True)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(600), nullable=True)  # pptx 파일 또는 png zip
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    card_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    png_width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    png_height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    validation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_state: Mapped[str | None] = mapped_column(String(30), nullable=True)  # 출력 시점의 내부 승인 상태
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
