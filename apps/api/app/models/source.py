from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import TimestampMixin, UUIDPKMixin
from app.models.enums import FieldCode, SourceType


class Source(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "sources"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 출처 자체의 '고정 분야' — 개별 문서의 실제 분야(SourceDocument.field_code)와는 구분된다.
    # 하나의 출처가 여러 분야의 문서를 낼 수 있으므로 문서 쪽 필드가 우선한다.
    field_code: Mapped[FieldCode] = mapped_column(Enum(FieldCode, native_enum=False), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 예: US, KR, JP, EU, INT
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False), nullable=False)
    # source_type=API일 때 어떤 응답 스키마로 파싱할지 고르는 키(예: "federal_register").
    # 공급자별로 JSON 구조가 다르므로 범용 API 수집기 대신 공급자별 파서를 레지스트리로 관리한다.
    api_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_primary_source: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 정부·국제기구·표준화기관 등 1차 출처 여부
    reliability_tier: Mapped[int] = mapped_column(default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 수집 실패가 반복되어도 자동으로 비활성화하지 않는다 — 대신 관리자 확인이 필요하다고만 표시한다.
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_collection_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
