from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import FieldCode, SourceType


class Source(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_name: Mapped[str] = mapped_column(String(200), nullable=False)
    field_code: Mapped[FieldCode] = mapped_column(Enum(FieldCode, native_enum=False), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False), nullable=False)
    reliability_tier: Mapped[int] = mapped_column(default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
