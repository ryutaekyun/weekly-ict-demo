import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ApprovableType, ApprovalDecision


class Approval(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "approvals"

    approvable_type: Mapped[ApprovableType] = mapped_column(
        Enum(ApprovableType, native_enum=False), nullable=False
    )
    approvable_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    approver_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(Enum(ApprovalDecision, native_enum=False), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
