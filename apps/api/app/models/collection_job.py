import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import CollectionJobStatus


class CollectionJob(Base, UUIDPKMixin, TimestampMixin):
    """'지금 수집'·예약 수집 1회의 작업 기록. 화면을 닫아도 서버(작업자)가 계속 처리하고, 상태는 이 표로 조회한다."""

    __tablename__ = "collection_jobs"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), nullable=False, index=True)
    status: Mapped[CollectionJobStatus] = mapped_column(Enum(CollectionJobStatus, native_enum=False, length=20), default=CollectionJobStatus.QUEUED, nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)  # manual | schedule
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 같은 정보원의 진행 중 작업을 1건으로 제한한다: 진행 중이면 source_id 문자열, 끝나면 NULL (유니크 제약으로 동시 중복 실행 차단)
    active_key: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stage: Mapped[str | None] = mapped_column(String(60), nullable=True)  # 연결 중 / 목록 분석 중 / 저장 중 / 분류 중 ...
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_duplicate: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    items_failed: Mapped[int] = mapped_column(Integer, default=0)
    items_classified: Mapped[int] = mapped_column(Integer, default=0)
    error_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("collection_runs.id"), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
