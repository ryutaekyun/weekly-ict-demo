import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import VerificationStatus


class EvidenceClaim(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "evidence_claims"

    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id"), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("source_documents.id"), nullable=True
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, native_enum=False), default=VerificationStatus.UNVERIFIED, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
