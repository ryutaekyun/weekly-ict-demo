import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import CandidateStatus, FieldCode


class CandidateCreate(BaseModel):
    field_code: FieldCode
    title: str
    summary: str | None = None
    source_document_id: uuid.UUID | None = None
    announced_date: date | None = None
    source_org: str | None = None
    recommended_reason: str | None = None


class CandidateUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    announced_date: date | None = None
    source_org: str | None = None
    recommended_reason: str | None = None
    status: CandidateStatus | None = None


class CandidateReviewCreate(BaseModel):
    comment_text: str
    is_final_approval: bool = False
    decided_status: CandidateStatus | None = None


class CandidateReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reviewer_user_id: uuid.UUID
    comment_text: str
    is_final_approval: bool
    decided_status: CandidateStatus | None
    created_at: datetime


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    field_code: FieldCode
    title: str
    summary: str | None
    announced_date: date | None
    source_org: str | None
    recommended_reason: str | None
    status: CandidateStatus
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CandidateDetailOut(CandidateOut):
    reviews: list[CandidateReviewOut] = []
