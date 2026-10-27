import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.collection_run import CollectionRun
from app.models.enums import FieldCode, UserRole
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.schemas.source import (
    CollectionRunOut,
    SourceCreate,
    SourceDocumentOut,
    SourceOut,
    SourceStatsOut,
    SourceUpdate,
)
from app.services.collection import run_collection

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=list[SourceOut])
def list_sources(
    field_code: FieldCode | None = None,
    needs_review: bool | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Source)
    if field_code is not None:
        stmt = stmt.where(Source.field_code == field_code)
    if needs_review is not None:
        stmt = stmt.where(Source.needs_review == needs_review)
    return db.scalars(stmt.order_by(Source.field_code)).all()


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SOURCE_ADMIN)),
):
    source = Source(**payload.model_dump())
    db.add(source)
    db.flush()
    log_action(
        db,
        actor_user_id=current_user.id,
        action="source.create",
        entity_type="source",
        entity_id=source.id,
        detail={"name": source.name, "url": source.url},
    )
    db.commit()
    db.refresh(source)
    return source


def _get_source_or_404(db: Session, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="출처를 찾을 수 없습니다")
    return source


@router.get("/{source_id}", response_model=SourceStatsOut)
def get_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    source = _get_source_or_404(db, source_id)
    document_count = db.scalar(
        select(func.count()).select_from(SourceDocument).where(SourceDocument.source_id == source_id)
    )
    last_run = db.scalar(
        select(CollectionRun)
        .where(CollectionRun.source_id == source_id)
        .order_by(CollectionRun.started_at.desc())
        .limit(1)
    )
    data = SourceOut.model_validate(source).model_dump()
    data["document_count"] = document_count or 0
    data["last_run_status"] = last_run.status if last_run else None
    return SourceStatsOut(**data)


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SOURCE_ADMIN)),
):
    source = _get_source_or_404(db, source_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(source, field, value)
    log_action(
        db,
        actor_user_id=current_user.id,
        action="source.update",
        entity_type="source",
        entity_id=source.id,
        detail=data,
    )
    db.commit()
    db.refresh(source)
    return source


@router.post("/{source_id}/collect", response_model=CollectionRunOut)
def trigger_collection(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.SOURCE_ADMIN, UserRole.APPROVER, UserRole.REVIEWER)),
):
    source = _get_source_or_404(db, source_id)
    if not source.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="비활성 출처는 수집할 수 없습니다")

    run = run_collection(db, source)
    log_action(
        db,
        actor_user_id=current_user.id,
        action="source.collect",
        entity_type="source",
        entity_id=source.id,
        detail={
            "status": run.status.value,
            "items_new": run.items_new,
            "items_duplicate": run.items_duplicate,
            "items_updated": run.items_updated,
        },
    )
    db.commit()
    return run


@router.get("/{source_id}/runs", response_model=list[CollectionRunOut])
def list_runs(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_source_or_404(db, source_id)
    stmt = select(CollectionRun).where(CollectionRun.source_id == source_id).order_by(CollectionRun.started_at.desc())
    return db.scalars(stmt).all()


@router.get("/{source_id}/documents", response_model=list[SourceDocumentOut])
def list_documents(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    _get_source_or_404(db, source_id)
    # collected_at으로 정렬하면 한 번의 수집 실행에서 들어온 문서들의 insert 순서가
    # 사실상 임의로 보여 "최신 문서"와 다른 순서로 나올 수 있다 — 발표일 기준으로 정렬한다.
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_id == source_id)
        .order_by(SourceDocument.published_at.desc().nulls_last(), SourceDocument.collected_at.desc())
    )
    return db.scalars(stmt).all()
