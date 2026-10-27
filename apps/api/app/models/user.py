from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import UserRole


class User(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, native_enum=False, length=30), nullable=False)
    job_title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", server_default="approved", nullable=False)
    favorite_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 내 관심 ICT 분야(JSON 목록)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_via: Mapped[str] = mapped_column(String(20), default="seed", server_default="seed", nullable=False)  # self | invite | seed
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
