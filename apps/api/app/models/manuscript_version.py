import uuid

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin


class ManuscriptVersion(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "manuscript_versions"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    body_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    edited_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    change_note: Mapped[str | None] = mapped_column(Text, nullable=True)
