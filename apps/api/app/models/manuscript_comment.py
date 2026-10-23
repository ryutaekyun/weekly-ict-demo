import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import ReviewCommentStatus


class ManuscriptComment(Base, UUIDPKMixin, TimestampMixin):
    """문단별 검토의견 1건. parent_comment_id가 있으면 그 의견에 대한 답변(스레드)이다."""

    __tablename__ = "manuscript_comments"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id"), nullable=False)
    author_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    parent_comment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("manuscript_comments.id"), nullable=True)
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 의견이 달린 문단의 스냅샷
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReviewCommentStatus] = mapped_column(
        Enum(ReviewCommentStatus, native_enum=False), default=ReviewCommentStatus.OPEN, nullable=False
    )
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
