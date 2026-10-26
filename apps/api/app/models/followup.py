import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class FollowupNotice(Base, UUIDPKMixin, TimestampMixin):
    """후속 규정 알림 — 이미 근거로 쓰인 원문을 바꾸는(시행일 연기·정정 등) 후속 공식 문서가 발견됐다는 기록.

    알림은 원고·보고서·카드뉴스의 내용이나 검증 상태를 자동으로 바꾸지 않는다.
    영향받는 산출물에 '후속 규정 발견·재검토 필요'를 표시하고, 연구원이 확인(ack)해야 해소된다.
    """

    __tablename__ = "followup_notices"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    original_doc_number: Mapped[str] = mapped_column(String(100), nullable=False)  # 영향받는 기존 문서 번호(예: 2024-28707)
    original_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    followup_doc_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    followup_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    followup_org: Mapped[str | None] = mapped_column(String(200), nullable=True)
    followup_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    followup_effective_on: Mapped[str | None] = mapped_column(String(20), nullable=True)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False)
    changes_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # [{"item","old","new"}]
    is_pilot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)


class FollowupAck(Base, UUIDPKMixin, TimestampMixin):
    """연구원이 영향받는 산출물에 대해 후속 규정을 확인했음을 남기는 기록(자동 검증 아님)."""

    __tablename__ = "followup_acks"

    notice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("followup_notices.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # manuscript / report / card_news
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)  # updated / no_change
    note: Mapped[str] = mapped_column(Text, nullable=False)
    acked_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
