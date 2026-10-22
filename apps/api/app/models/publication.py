import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import PublicationChannel


class Publication(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "publications"

    edition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("editions.id"), nullable=False)
    channel: Mapped[PublicationChannel] = mapped_column(
        Enum(PublicationChannel, native_enum=False), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recipient_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", nullable=False)
