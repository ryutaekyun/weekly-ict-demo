import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    CollectionErrorType,
    CollectionRunStatus,
    DocumentType,
    FieldCode,
    SourceDocumentStatus,
    SourceType,
)


class SourceCreate(BaseModel):
    name: str
    org_name: str
    field_code: FieldCode
    url: str
    source_type: SourceType = SourceType.RSS
    api_provider: str | None = None
    country_code: str | None = None
    is_primary_source: bool = False
    reliability_tier: int = 1


class SourceUpdate(BaseModel):
    name: str | None = None
    org_name: str | None = None
    field_code: FieldCode | None = None
    url: str | None = None
    is_primary_source: bool | None = None
    reliability_tier: int | None = None
    is_active: bool | None = None
    needs_review: bool | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    org_name: str
    field_code: FieldCode
    country_code: str | None
    url: str
    source_type: SourceType
    api_provider: str | None
    is_primary_source: bool
    reliability_tier: int
    is_active: bool
    needs_review: bool
    consecutive_failures: int
    last_attempted_at: datetime | None
    last_successful_collection_at: datetime | None
    created_at: datetime


class SourceStatsOut(SourceOut):
    document_count: int
    last_run_status: CollectionRunStatus | None = None


class SourceDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    title: str
    origin_url: str
    attachment_url: str | None
    published_at: datetime | None
    document_updated_at: datetime | None
    collected_at: datetime
    raw_text: str | None
    language: str | None
    country_code: str | None
    document_type: DocumentType
    field_code: FieldCode
    collection_method: SourceType
    is_peer_reviewed: bool | None
    requires_primary_source_check: bool
    content_hash: str
    status: SourceDocumentStatus
    duplicate_of_id: uuid.UUID | None
    previous_version_id: uuid.UUID | None


class CollectionRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: CollectionRunStatus
    items_found: int
    items_new: int
    items_duplicate: int
    items_updated: int
    error_message: str | None
    error_type: CollectionErrorType | None
    retry_count: int
