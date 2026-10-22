import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import CollectionRunStatus, FieldCode, SourceDocumentStatus, SourceType


class SourceCreate(BaseModel):
    name: str
    org_name: str
    field_code: FieldCode
    url: str
    source_type: SourceType = SourceType.RSS
    reliability_tier: int = 1


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    org_name: str
    field_code: FieldCode
    url: str
    source_type: SourceType
    reliability_tier: int
    is_active: bool
    created_at: datetime


class SourceDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    title: str
    origin_url: str
    published_at: datetime | None
    collected_at: datetime
    content_hash: str
    status: SourceDocumentStatus
    duplicate_of_id: uuid.UUID | None


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
    error_message: str | None
    retry_count: int
