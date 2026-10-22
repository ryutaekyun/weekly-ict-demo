import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import CandidateStatus


class CandidateReview(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "candidate_reviews"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_final_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    decided_status: Mapped[CandidateStatus | None] = mapped_column(
        Enum(CandidateStatus, native_enum=False), nullable=True
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="reviews")
