from datetime import date

from sqlalchemy import Date, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import PublicationType


class Edition(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "editions"

    publication_type: Mapped[PublicationType] = mapped_column(
        Enum(PublicationType, native_enum=False), nullable=False
    )
    edition_label: Mapped[str] = mapped_column(String(100), nullable=False)
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="planned", nullable=False)
