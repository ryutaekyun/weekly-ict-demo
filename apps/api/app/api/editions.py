import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.edition import Edition
from app.models.enums import UserRole
from app.models.manuscript import Manuscript
from app.models.user import User
from app.schemas.manuscript import EditionCreate, EditionOut, EditionUpdate

router = APIRouter(prefix="/editions", tags=["editions"])


def _with_count(db: Session, edition: Edition) -> EditionOut:
    count = db.scalar(select(func.count()).select_from(Manuscript).where(Manuscript.edition_id == edition.id))
    data = EditionOut.model_validate(edition).model_dump()
    data["manuscript_count"] = count or 0
    return EditionOut(**data)


@router.get("", response_model=list[EditionOut])
def list_editions(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    editions = db.scalars(select(Edition).order_by(Edition.target_date.desc())).all()
    return [_with_count(db, e) for e in editions]


@router.post("", response_model=EditionOut, status_code=status.HTTP_201_CREATED)
def create_edition(
    payload: EditionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER)),
):
    edition = Edition(**payload.model_dump())
    db.add(edition)
    db.flush()
    log_action(
        db, actor_user_id=current_user.id, action="edition.create", entity_type="edition", entity_id=edition.id,
        detail={"edition_label": edition.edition_label},
    )
    db.commit()
    db.refresh(edition)
    return _with_count(db, edition)


def _get_edition_or_404(db: Session, edition_id: uuid.UUID) -> Edition:
    edition = db.get(Edition, edition_id)
    if edition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="회차를 찾을 수 없습니다")
    return edition


@router.get("/{edition_id}", response_model=EditionOut)
def get_edition(
    edition_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return _with_count(db, _get_edition_or_404(db, edition_id))


@router.patch("/{edition_id}", response_model=EditionOut)
def update_edition(
    edition_id: uuid.UUID,
    payload: EditionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER)),
):
    edition = _get_edition_or_404(db, edition_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(edition, field, value)
    log_action(
        db, actor_user_id=current_user.id, action="edition.update", entity_type="edition", entity_id=edition.id,
        detail=data,
    )
    db.commit()
    db.refresh(edition)
    return _with_count(db, edition)
