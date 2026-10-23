import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class ManuscriptVersion(Base, UUIDPKMixin, TimestampMixin):
    """일반 자동저장마다 쌓지 않는다 — is_milestone=True(수동 '버전 저장' 또는 상태 전환 시점)만
    항상 남기고, 자동저장은 일정 시간 간격을 두고 내용이 실제로 바뀐 경우에만 기록한다."""

    __tablename__ = "manuscript_versions"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    body_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    body_json_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
