import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import IitpSelectionStatus, ManuscriptStatus


class Manuscript(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """실제 집필 단위 1건 — 일반호 기준 하나의 회차(Edition)에 유형별(주요 이슈/주요국 동향/
    분야별 단신/향후 일정/요약문, manuscript_type에 저장) 원고가 여러 건 연결된다."""

    __tablename__ = "manuscripts"

    edition_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("editions.id"), nullable=True)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(500), nullable=True)  # 국문·영문 제목 병기 지원

    # body: 검색·미리보기용 평문. body_json: TipTap(ProseMirror) 구조화 문서(JSON 문자열) —
    # 각주 마크(footnoteId 속성 포함)를 포함한 실제 편집 원본. HTML을 직접 저장하지 않아
    # 임의 스크립트가 섞여 들어갈 여지를 원천적으로 막는다.
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    manuscript_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ManuscriptStatus] = mapped_column(
        Enum(ManuscriptStatus, native_enum=False), default=ManuscriptStatus.DRAFT, nullable=False
    )

    lock_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 낙관적 잠금(동시수정 충돌 감지)
    is_pilot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 시범 작성 원고 — 실제 발간 원고 아님

    # IITP 공식 선정 여부 — 내부 확정(status=approved)과 반드시 구분해 기록한다.
    iitp_selection_status: Mapped[IitpSelectionStatus] = mapped_column(
        Enum(IitpSelectionStatus, native_enum=False), default=IitpSelectionStatus.NOT_SUBMITTED, nullable=False
    )
    iitp_selection_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    iitp_confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    iitp_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
