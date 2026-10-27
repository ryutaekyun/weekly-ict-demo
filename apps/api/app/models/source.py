from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, Integer, String, Text
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
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, native_enum=False, length=20), nullable=False)
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

    # ---- Phase 4-2 운영 설정 ----
    interval_minutes: Mapped[int] = mapped_column(Integer, default=1440, server_default="1440", nullable=False)  # 자동 수집 주기(분)
    min_request_interval_seconds: Mapped[float] = mapped_column(Float, default=3.0, server_default="3.0", nullable=False)  # 같은 호스트 요청 최소 간격(arXiv 등 공식 안내 준수)
    respect_robots: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    # 접속 상태: ok(정상 수집) / metadata_only / blocked(접속 제한) / moved(주소 변경) / unverified(미검증) / error(일시 오류)
    access_status: Mapped[str] = mapped_column(String(20), default="unverified", server_default="unverified", nullable=False)
    access_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_new_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # html/pdf/metadata 방식의 추가 설정(링크 패턴·제목 등)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
