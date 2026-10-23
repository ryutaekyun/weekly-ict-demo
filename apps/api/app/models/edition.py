import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, String
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

    # Phase 3-1 추가 — 실제 IITP 발간 업무 단위(회차) 관리
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edition_number: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 연중 몇 회차인지
    is_special: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 일반호/특집호 구분
    theme_title: Mapped[str | None] = mapped_column(String(300), nullable=True)  # 특집호 주제명
    lead_researcher_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
