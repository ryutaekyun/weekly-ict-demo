import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportCreate(BaseModel):
    report_type: Literal["general", "special", "summary"]
    title: str = Field(min_length=1, max_length=500)
    title_en: str | None = None
    edition_id: uuid.UUID | None = None
    publish_date: datetime | None = None


class ReportUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    title_en: str | None = None
    edition_id: uuid.UUID | None = None
    publish_date: datetime | None = None
    template_id: uuid.UUID | None = None


class ReportItemCreate(BaseModel):
    part_key: str | None = None
    heading: str | None = None
    manuscript_id: uuid.UUID


class SummaryItemCreate(BaseModel):
    part_key: Literal["key_issue", "country_trend", "key_message"]
    manuscript_id: uuid.UUID
    source_sentence: str = Field(min_length=1)


class ReportItemUpdate(BaseModel):
    heading: str | None = None
    summary_text: str | None = None
    part_key: str | None = None


class ReorderRequest(BaseModel):
    item_ids: list[uuid.UUID]


class FinalizeRequest(BaseModel):
    exception_reason: str | None = None


class ExportRequest(BaseModel):
    file_format: Literal["docx", "pdf"]


class ReportItemOut(BaseModel):
    id: uuid.UUID
    position: int
    part_key: str | None
    heading: str | None
    manuscript_id: uuid.UUID | None
    manuscript_title: str | None
    manuscript_status: str | None
    summary_text: str | None
    source_sentence: str | None
    needs_review: bool = False


class ReportListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_type: str
    title: str
    status: str
    edition_id: uuid.UUID | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ReportExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    report_id: uuid.UUID
    file_format: str
    status: str
    error_message: str | None
    template_version: int | None
    file_name: str | None
    file_sha256: str | None
    file_size: int | None
    page_count: int | None
    footnote_count: int | None
    table_count: int | None
    is_final: bool
    created_by_user_id: uuid.UUID
    created_at: datetime
    finished_at: datetime | None
    manuscript_versions_json: str | None
    validation_json: str | None


class PreflightIssue(BaseModel):
    level: str
    code: str
    message: str
    part: str | None = None


class ReportDetailOut(ReportListItemOut):
    title_en: str | None
    publish_date: datetime | None
    template_id: uuid.UUID | None
    iitp_confirmed: bool
    finalize_exception_reason: str | None
    finalized_at: datetime | None
    items: list[ReportItemOut]
    preflight: list[PreflightIssue]
    blocking: list[PreflightIssue]


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: int
    is_active: bool
    is_provisional: bool
    config_json: str
    created_at: datetime


class TemplateConfigPatch(BaseModel):
    config: dict
