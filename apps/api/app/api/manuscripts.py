import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.candidate import Candidate
from app.models.enums import ManuscriptStatus, UserRole
from app.models.manuscript import Manuscript
from app.models.manuscript_comment import ManuscriptComment
from app.models.manuscript_footnote import ManuscriptFootnote
from app.models.manuscript_version import ManuscriptVersion
from app.models.user import User
from app.schemas.manuscript import (
    CommentCreate,
    CommentOut,
    FootnoteCreate,
    FootnoteOut,
    FootnoteUpdate,
    IitpSelectionUpdate,
    ManuscriptApprovalRequest,
    ManuscriptBodyUpdate,
    ManuscriptChangesRequest,
    ManuscriptCreate,
    ManuscriptDetailOut,
    ManuscriptListItemOut,
    ManuscriptReviewRequest,
    ManuscriptVersionListItemOut,
    ManuscriptVersionOut,
    NeedsReexaminationOut,
)
from app.services import manuscript_comment_service, manuscript_footnote_service, manuscript_service
from app.services.manuscript_service import ManuscriptConflictError

router = APIRouter(prefix="/manuscripts", tags=["manuscripts"])

REVIEWER_ROLES = (UserRole.ADMIN, UserRole.APPROVER, UserRole.REVIEWER)
APPROVER_ROLES = (UserRole.ADMIN, UserRole.APPROVER)


def _get_manuscript_or_404(db: Session, manuscript_id: uuid.UUID) -> Manuscript:
    manuscript = db.get(Manuscript, manuscript_id)
    if manuscript is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="원고를 찾을 수 없습니다")
    return manuscript


def _detail_out(db: Session, manuscript: Manuscript) -> ManuscriptDetailOut:
    flagged, reason = manuscript_service.compute_needs_reexamination(db, manuscript)
    total, verified = manuscript_service.footnote_verification_summary(db, manuscript.id)
    data = ManuscriptListItemOut.model_validate(manuscript).model_dump()
    return ManuscriptDetailOut(
        **data, body=manuscript.body, body_json=manuscript.body_json,
        iitp_selection_note=manuscript.iitp_selection_note,
        iitp_confirmed_by_user_id=manuscript.iitp_confirmed_by_user_id,
        iitp_confirmed_at=manuscript.iitp_confirmed_at,
        needs_reexamination=NeedsReexaminationOut(flagged=flagged, reason=reason),
        footnote_verification_total=total, footnote_verification_verified=verified,
    )


def _assert_author_or_privileged(manuscript: Manuscript, user: User) -> None:
    if manuscript.author_user_id != user.id and user.role not in REVIEWER_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="본인이 작성한 원고만 수정할 수 있습니다")


@router.post("", response_model=ManuscriptDetailOut, status_code=status.HTTP_201_CREATED)
def create_manuscript(
    payload: ManuscriptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.candidate_id is not None:
        candidate = db.get(Candidate, payload.candidate_id)
        if candidate is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="후보주제를 찾을 수 없습니다")

    manuscript = manuscript_service.create_manuscript(
        db, author_user_id=current_user.id, title=payload.title, manuscript_type=payload.manuscript_type,
        candidate_id=payload.candidate_id, edition_id=payload.edition_id, is_pilot=payload.is_pilot,
    )
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.create", entity_type="manuscript",
        entity_id=manuscript.id, detail={"candidate_id": str(payload.candidate_id) if payload.candidate_id else None},
    )
    db.commit()
    return _detail_out(db, manuscript)


@router.get("", response_model=list[ManuscriptListItemOut])
def list_manuscripts(
    edition_id: uuid.UUID | None = None,
    status_filter: ManuscriptStatus | None = None,
    candidate_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Manuscript)
    if edition_id is not None:
        stmt = stmt.where(Manuscript.edition_id == edition_id)
    if status_filter is not None:
        stmt = stmt.where(Manuscript.status == status_filter)
    if candidate_id is not None:
        stmt = stmt.where(Manuscript.candidate_id == candidate_id)
    stmt = stmt.order_by(Manuscript.updated_at.desc())
    return db.scalars(stmt).all()


@router.get("/{manuscript_id}", response_model=ManuscriptDetailOut)
def get_manuscript(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    return _detail_out(db, manuscript)


@router.get("/{manuscript_id}/context")
def get_manuscript_context(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """오른쪽 '원문·근거자료 패널'에 필요한 참고자료 묶음 — 후보주제·이슈분석·관련 원문을 한 번에 내려준다."""
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    if manuscript.candidate_id is None:
        return {"candidate": None, "issue": None}

    candidate = db.get(Candidate, manuscript.candidate_id)
    if candidate is None:
        return {"candidate": None, "issue": None}

    from app.api.candidates import get_candidate as _get_candidate_detail
    from app.api.issues import get_issue_detail as _get_issue_detail

    candidate_out = _get_candidate_detail(candidate.id, db=db, _=_)
    issue_out = None
    if candidate.issue_cluster_id is not None:
        try:
            issue_out = _get_issue_detail(candidate.issue_cluster_id, db=db, _=_)
        except HTTPException:
            issue_out = None
    return {"candidate": candidate_out, "issue": issue_out}


@router.patch("/{manuscript_id}", response_model=ManuscriptDetailOut)
def update_manuscript_body(
    manuscript_id: uuid.UUID,
    payload: ManuscriptBodyUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    _assert_author_or_privileged(manuscript, current_user)
    try:
        manuscript_service.update_manuscript_body(
            db, manuscript, title=payload.title, title_en=payload.title_en, body_json=payload.body_json,
            body=payload.body, lock_version=payload.lock_version, actor_user_id=current_user.id,
            change_note=payload.change_note, is_milestone=payload.is_milestone,
        )
    except ManuscriptConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    return _detail_out(db, manuscript)


@router.get("/{manuscript_id}/lint")
def lint_manuscript(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """무료 규칙 기반 작성 점검 — 근거 일치·날짜 역할·수치·중복 경고(원고를 바꾸지 않음)."""
    from app.services import manuscript_lint

    return manuscript_lint.lint(db, _get_manuscript_or_404(db, manuscript_id))


@router.get("/{manuscript_id}/versions", response_model=list[ManuscriptVersionListItemOut])
def list_versions(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_manuscript_or_404(db, manuscript_id)
    stmt = (
        select(ManuscriptVersion).where(ManuscriptVersion.manuscript_id == manuscript_id)
        .order_by(ManuscriptVersion.version_no.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{manuscript_id}/versions/{version_id}", response_model=ManuscriptVersionOut)
def get_version(
    manuscript_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    version = db.get(ManuscriptVersion, version_id)
    if version is None or version.manuscript_id != manuscript_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="버전을 찾을 수 없습니다")
    return version


@router.post("/{manuscript_id}/versions/{version_id}/restore", response_model=ManuscriptDetailOut)
def restore_version(
    manuscript_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    _assert_author_or_privileged(manuscript, current_user)
    version = db.get(ManuscriptVersion, version_id)
    if version is None or version.manuscript_id != manuscript_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="버전을 찾을 수 없습니다")
    manuscript_service.restore_version(db, manuscript, version, actor_user_id=current_user.id)
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.version.restore", entity_type="manuscript",
        entity_id=manuscript.id, detail={"restored_version_no": version.version_no},
    )
    db.commit()
    return _detail_out(db, manuscript)


@router.post("/{manuscript_id}/review-request", response_model=ManuscriptDetailOut)
def request_review(
    manuscript_id: uuid.UUID,
    payload: ManuscriptReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    _assert_author_or_privileged(manuscript, current_user)
    reviewer = db.get(User, payload.reviewer_user_id)
    if reviewer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="검토자를 찾을 수 없습니다")
    manuscript_service.request_review(db, manuscript, reviewer_user_id=payload.reviewer_user_id)
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.review_request", entity_type="manuscript",
        entity_id=manuscript.id, detail={"reviewer_user_id": str(payload.reviewer_user_id)},
    )
    db.commit()
    return _detail_out(db, manuscript)


@router.post("/{manuscript_id}/request-changes", response_model=ManuscriptDetailOut)
def request_changes(
    manuscript_id: uuid.UUID,
    payload: ManuscriptChangesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*REVIEWER_ROLES)),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    manuscript_service.request_changes(db, manuscript)
    manuscript_comment_service.create_comment(
        db, manuscript_id=manuscript.id, author_user_id=current_user.id, comment_text=payload.comment_text,
    )
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.request_changes", entity_type="manuscript",
        entity_id=manuscript.id, detail={"comment": payload.comment_text},
    )
    db.commit()
    return _detail_out(db, manuscript)


@router.post("/{manuscript_id}/approve", response_model=ManuscriptDetailOut)
def approve_manuscript(
    manuscript_id: uuid.UUID,
    payload: ManuscriptApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    manuscript_service.approve_internal(db, manuscript, approver_user_id=current_user.id, comment=payload.comment)
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.approve", entity_type="manuscript",
        entity_id=manuscript.id, detail={"comment": payload.comment},
    )
    db.commit()
    return _detail_out(db, manuscript)


@router.post("/{manuscript_id}/reopen", response_model=ManuscriptDetailOut)
def reopen_manuscript(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    manuscript_service.reopen_for_edit(db, manuscript)
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.reopen", entity_type="manuscript", entity_id=manuscript.id,
        detail={},
    )
    db.commit()
    return _detail_out(db, manuscript)


@router.patch("/{manuscript_id}/iitp-selection", response_model=ManuscriptDetailOut)
def update_iitp_selection(
    manuscript_id: uuid.UUID,
    payload: IitpSelectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*APPROVER_ROLES)),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    manuscript_service.record_iitp_selection(
        db, manuscript, status_value=payload.iitp_selection_status, note=payload.iitp_selection_note,
        actor_user_id=current_user.id,
    )
    log_action(
        db, actor_user_id=current_user.id, action="manuscript.iitp_selection", entity_type="manuscript",
        entity_id=manuscript.id, detail={"status": payload.iitp_selection_status.value},
    )
    db.commit()
    return _detail_out(db, manuscript)


# --- Footnotes -----------------------------------------------------------------


@router.get("/{manuscript_id}/footnotes", response_model=list[FootnoteOut])
def list_footnotes(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_manuscript_or_404(db, manuscript_id)
    stmt = select(ManuscriptFootnote).where(ManuscriptFootnote.manuscript_id == manuscript_id)
    return db.scalars(stmt).all()


@router.post("/{manuscript_id}/footnotes", response_model=FootnoteOut, status_code=status.HTTP_201_CREATED)
def create_footnote(
    manuscript_id: uuid.UUID,
    payload: FootnoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    _assert_author_or_privileged(manuscript, current_user)
    footnote = manuscript_footnote_service.create_footnote(
        db, manuscript_id=manuscript_id, created_by_user_id=current_user.id, **payload.model_dump(),
    )
    db.commit()
    return footnote


@router.patch("/{manuscript_id}/footnotes/{footnote_id}", response_model=FootnoteOut)
def update_footnote(
    manuscript_id: uuid.UUID,
    footnote_id: uuid.UUID,
    payload: FootnoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    _assert_author_or_privileged(manuscript, current_user)
    footnote = db.get(ManuscriptFootnote, footnote_id)
    if footnote is None or footnote.manuscript_id != manuscript_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="각주를 찾을 수 없습니다")
    manuscript_footnote_service.update_footnote(db, footnote, **payload.model_dump())
    db.commit()
    return footnote


@router.post("/{manuscript_id}/footnotes/{footnote_id}/verify", response_model=FootnoteOut)
def verify_footnote(
    manuscript_id: uuid.UUID,
    footnote_id: uuid.UUID,
    matched: bool,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    footnote = db.get(ManuscriptFootnote, footnote_id)
    if footnote is None or footnote.manuscript_id != manuscript_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="각주를 찾을 수 없습니다")
    manuscript_footnote_service.verify_footnote(db, footnote, verifier_user_id=current_user.id, matched=matched)
    db.commit()
    return footnote


@router.delete("/{manuscript_id}/footnotes/{footnote_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_footnote(
    manuscript_id: uuid.UUID,
    footnote_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    manuscript = _get_manuscript_or_404(db, manuscript_id)
    _assert_author_or_privileged(manuscript, current_user)
    footnote = db.get(ManuscriptFootnote, footnote_id)
    if footnote is None or footnote.manuscript_id != manuscript_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="각주를 찾을 수 없습니다")
    db.delete(footnote)
    db.commit()


# --- Comments -----------------------------------------------------------------


@router.get("/{manuscript_id}/comments", response_model=list[CommentOut])
def list_comments(
    manuscript_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_manuscript_or_404(db, manuscript_id)
    stmt = (
        select(ManuscriptComment).where(ManuscriptComment.manuscript_id == manuscript_id)
        .order_by(ManuscriptComment.created_at)
    )
    return db.scalars(stmt).all()


@router.post("/{manuscript_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
def create_comment(
    manuscript_id: uuid.UUID,
    payload: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_manuscript_or_404(db, manuscript_id)
    comment = manuscript_comment_service.create_comment(
        db, manuscript_id=manuscript_id, author_user_id=current_user.id, comment_text=payload.comment_text,
        anchor_text=payload.anchor_text, parent_comment_id=payload.parent_comment_id,
    )
    db.commit()
    return comment


@router.post("/{manuscript_id}/comments/{comment_id}/resolve", response_model=CommentOut)
def resolve_comment(
    manuscript_id: uuid.UUID,
    comment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.get(ManuscriptComment, comment_id)
    if comment is None or comment.manuscript_id != manuscript_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="검토의견을 찾을 수 없습니다")
    manuscript_comment_service.resolve_comment(db, comment, resolver_user_id=current_user.id)
    db.commit()
    return comment
