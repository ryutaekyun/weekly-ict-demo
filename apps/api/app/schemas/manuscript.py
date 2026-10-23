import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    EvidenceMatchStatus,
    IitpSelectionStatus,
    ManuscriptStatus,
    PublicationType,
    ReviewCommentStatus,
)

# --- Edition ---------------------------------------------------------------


class EditionCreate(BaseModel):
    publication_type: PublicationType = PublicationType.WEEKLY_REPORT
    edition_label: str
    target_date: date
    fiscal_year: int | None = None
    edition_number: int | None = None
    is_special: bool = False
    theme_title: str | None = None
    lead_researcher_user_id: uuid.UUID | None = None
    reviewer_user_id: uuid.UUID | None = None


class EditionUpdate(BaseModel):
    edition_label: str | None = None
    target_date: date | None = None
    status: str | None = None
    theme_title: str | None = None
    lead_researcher_user_id: uuid.UUID | None = None
    reviewer_user_id: uuid.UUID | None = None


class EditionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    publication_type: PublicationType
    edition_label: str
    target_date: date
    status: str
    fiscal_year: int | None
    edition_number: int | None
    is_special: bool
    theme_title: str | None
    lead_researcher_user_id: uuid.UUID | None
    reviewer_user_id: uuid.UUID | None
    manuscript_count: int = 0


# --- Manuscript --------------------------------------------------------------


class ManuscriptCreate(BaseModel):
    candidate_id: uuid.UUID | None = None
    edition_id: uuid.UUID | None = None
    manuscript_type: str  # ManuscriptSectionKind 값 또는 자유 문자열(특집호 custom)
    title: str
    is_pilot: bool = False


class ManuscriptListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    edition_id: uuid.UUID | None
    candidate_id: uuid.UUID | None
    author_user_id: uuid.UUID
    reviewer_user_id: uuid.UUID | None
    title: str
    title_en: str | None
    manuscript_type: str
    status: ManuscriptStatus
    is_pilot: bool
    iitp_selection_status: IitpSelectionStatus
    lock_version: int
    created_at: datetime
    updated_at: datetime


class NeedsReexaminationOut(BaseModel):
    flagged: bool
    reason: str | None = None


class ManuscriptDetailOut(ManuscriptListItemOut):
    body: str | None
    body_json: str | None
    iitp_selection_note: str | None
    iitp_confirmed_by_user_id: uuid.UUID | None
    iitp_confirmed_at: datetime | None
    needs_reexamination: NeedsReexaminationOut
    footnote_verification_total: int
    footnote_verification_verified: int


class ManuscriptBodyUpdate(BaseModel):
    title: str | None = None
    title_en: str | None = None
    body_json: str
    body: str  # 검색·미리보기용 평문(프런트에서 body_json으로부터 추출해 함께 전송)
    lock_version: int  # 낙관적 잠금 — 현재 클라이언트가 들고 있던 버전
    change_note: str | None = None
    is_milestone: bool = False


class ManuscriptReviewRequest(BaseModel):
    reviewer_user_id: uuid.UUID


class ManuscriptChangesRequest(BaseModel):
    comment_text: str


class ManuscriptApprovalRequest(BaseModel):
    comment: str | None = None


class IitpSelectionUpdate(BaseModel):
    iitp_selection_status: IitpSelectionStatus
    iitp_selection_note: str | None = None


# --- Manuscript Versions -----------------------------------------------------


class ManuscriptVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    manuscript_id: uuid.UUID
    version_no: int
    body_snapshot: str
    body_json_snapshot: str | None
    edited_by_user_id: uuid.UUID
    change_note: str | None
    is_milestone: bool
    created_at: datetime


class ManuscriptVersionListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_no: int
    edited_by_user_id: uuid.UUID
    change_note: str | None
    is_milestone: bool
    created_at: datetime


# --- Footnotes -----------------------------------------------------------------


class FootnoteCreate(BaseModel):
    mark_id: str
    anchor_text: str
    source_document_id: uuid.UUID | None = None
    source_url: str
    source_org: str | None = None
    excerpt: str | None = None
    location_label: str | None = None
    published_at: datetime | None = None


class FootnoteUpdate(BaseModel):
    anchor_text: str | None = None
    source_document_id: uuid.UUID | None = None
    source_url: str | None = None
    source_org: str | None = None
    excerpt: str | None = None
    location_label: str | None = None
    published_at: datetime | None = None


class FootnoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    manuscript_id: uuid.UUID
    mark_id: str
    anchor_text: str
    source_document_id: uuid.UUID | None
    source_url: str
    source_org: str | None
    excerpt: str | None
    location_label: str | None
    published_at: datetime | None
    accessed_at: datetime | None
    verification_status: EvidenceMatchStatus
    verified_by_user_id: uuid.UUID | None
    verified_at: datetime | None
    created_by_user_id: uuid.UUID
    updated_at: datetime


# --- Comments -----------------------------------------------------------------


class CommentCreate(BaseModel):
    anchor_text: str | None = None
    comment_text: str
    parent_comment_id: uuid.UUID | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    manuscript_id: uuid.UUID
    author_user_id: uuid.UUID
    parent_comment_id: uuid.UUID | None
    anchor_text: str | None
    comment_text: str
    status: ReviewCommentStatus
    resolved_by_user_id: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime
