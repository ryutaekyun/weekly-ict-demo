import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin, UpdatedAtMixin
from app.models.enums import EvidenceMatchStatus


class ManuscriptFootnote(Base, UUIDPKMixin, TimestampMixin, UpdatedAtMixin):
    """원고 문장 ↔ 원문 근거 연결 1건. 각주 번호는 저장하지 않고, 문서 내 mark_id 등장 순서로
    매번 다시 계산한다(문단 이동·삭제 후에도 번호가 어긋나지 않게 하기 위해).

    원문에서 확인되지 않은 내용을 임의로 검증완료 처리하지 않는다 — verification_status는
    연구원이 명시적으로 확인 버튼을 눌러야만 MATCHED로 바뀐다(기본값 NOT_VERIFIED)."""

    __tablename__ = "manuscript_footnotes"

    manuscript_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("manuscripts.id"), nullable=False)
    mark_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 본문 TipTap 마크의 footnoteId와 매칭
    anchor_text: Mapped[str] = mapped_column(Text, nullable=False)  # 연결 당시 문장 스냅샷(이후 편집돼도 근거 추적 가능)

    source_document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("source_documents.id"), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_org: Mapped[str | None] = mapped_column(String(200), nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)  # 근거 원문 발췌
    location_label: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 예: "3문단" — 없으면 "위치 미확인"

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 인용·열람일

    verification_status: Mapped[EvidenceMatchStatus] = mapped_column(
        Enum(EvidenceMatchStatus, native_enum=False), default=EvidenceMatchStatus.NOT_VERIFIED, nullable=False
    )
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
