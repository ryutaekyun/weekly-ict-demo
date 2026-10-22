import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import ManuscriptStatus


class Manuscript(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    __tablename__ = "manuscripts"

    edition_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("editions.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"), nullable=True)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    manuscript_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ManuscriptStatus] = mapped_column(
        Enum(ManuscriptStatus, native_enum=False), default=ManuscriptStatus.DRAFT, nullable=False
    )
