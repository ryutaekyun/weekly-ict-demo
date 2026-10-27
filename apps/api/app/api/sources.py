import json
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.db import get_db
from app.core.deps import get_current_user, require_roles
from app.models.audit_log import AuditLog
from app.models.collection_job import CollectionJob
from app.models.collection_run import CollectionRun
from app.models.document_classification import DocumentClassification
from app.models.enums import ACTIVE_JOB_STATUSES, ClassificationRelevance, CollectionJobStatus, FieldCode, SourceDocumentStatus, SourceType, UserRole
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.schemas.source import (
    CollectionJobOut,
    CollectionRunOut,
    CollectStartOut,
    ConnectionTestIn,
    SourceCreate,
    SourceDocumentOut,
    SourceOut,
    SourceStatsOut,
    SourceUpdate,
)
from app.services import collection_jobs, url_guard
from app.services.collection import API_PROVIDERS, access_status_for, classify_http_error, fetch_preview

router = APIRouter(prefix="/sources", tags=["sources"])
collection_router = APIRouter(prefix="/collection", tags=["collection"])

MANAGE = (UserRole.ADMIN, UserRole.SOURCE_ADMIN)
RUN = (UserRole.ADMIN, UserRole.SOURCE_ADMIN, UserRole.APPROVER, UserRole.REVIEWER)


def _validate_source_fields(url: str, source_type: SourceType, api_provider: str | None, config_json: str | None) -> None:
    try:
        url_guard.assert_safe_url(url, resolve=False)
    except url_guard.UnsafeURLError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if source_type == SourceType.API and api_provider not in API_PROVIDERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"지원하는 API 공급자만 선택할 수 있습니다: {', '.join(sorted(API_PROVIDERS))}")
    if config_json:
        try:
            if not isinstance(json.loads(config_json), dict):
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="추가 설정은 JSON 객체여야 합니다") from None


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
    return db.scalars(stmt.order_by(Source.field_code, Source.name)).all()


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: SourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
):
    _validate_source_fields(payload.url, payload.source_type, payload.api_provider, payload.config_json)
    source = Source(**payload.model_dump())
    if source.source_type == SourceType.METADATA:
        source.access_status = "metadata_only"
    db.add(source)
    db.flush()
    log_action(db, actor_user_id=current_user.id, action="source.create", entity_type="source", entity_id=source.id, detail={"name": source.name, "url": source.url, "type": source.source_type.value})
    db.commit()
    db.refresh(source)
    return source


@router.post("/test-connection")
def test_connection(payload: ConnectionTestIn, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*MANAGE))):
    """저장하지 않고 실제로 접속해 항목을 읽어 본다 — 접속 제한·주소 오류·형식 오류를 등록 전에 확인한다."""
    _validate_source_fields(payload.url, payload.source_type, payload.api_provider, payload.config_json)
    probe = Source(name="(연결 테스트)", org_name="-", field_code=FieldCode.AI, url=payload.url, source_type=payload.source_type, api_provider=payload.api_provider,
                   config_json=payload.config_json, respect_robots=payload.respect_robots, min_request_interval_seconds=payload.min_request_interval_seconds)
    try:
        entries = fetch_preview(probe)
        result = {"ok": True, "found": len(entries), "access_status": "ok", "message": f"접속 성공 — {len(entries)}건을 읽었습니다." if entries else "접속은 성공했지만 읽을 수 있는 항목이 없습니다(필터·주소 확인).",
                  "sample": [{"title": e.title, "link": e.link, "published_at": e.published_at.isoformat() if e.published_at else None, "external_id": e.external_id} for e in entries[:5]]}
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 그대로 화면에 보여 준다
        et = classify_http_error(exc)
        st, note = access_status_for(et, exc)
        result = {"ok": False, "found": 0, "access_status": st, "error_type": et.value, "message": note, "detail": f"{type(exc).__name__}: {exc}"[:500], "sample": []}
    log_action(db, actor_user_id=current_user.id, action="source.test_connection", entity_type="source", entity_id=uuid.uuid4(), detail={"url": payload.url, "ok": result["ok"]})
    db.commit()
    return result


def _get_source_or_404(db: Session, source_id: uuid.UUID) -> Source:
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="출처를 찾을 수 없습니다")
    return source


@router.get("/jobs/{job_id}", response_model=CollectionJobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    job = db.get(CollectionJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="수집 작업을 찾을 수 없습니다")
    return _job_out(job)


@router.post("/jobs/{job_id}/cancel", response_model=CollectionJobOut)
def cancel_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_roles(*RUN))):
    job = db.get(CollectionJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="수집 작업을 찾을 수 없습니다")
    if job.status not in ACTIVE_JOB_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 끝난 작업은 취소할 수 없습니다")
    collection_jobs.request_cancel(db, job)
    log_action(db, actor_user_id=current_user.id, action="source.collect.cancel", entity_type="source", entity_id=job.source_id, detail={"job_id": str(job.id)})
    db.commit()
    db.refresh(job)
    return _job_out(job)


def _job_out(job: CollectionJob) -> CollectionJobOut:
    return CollectionJobOut(**{**{c: getattr(job, c) for c in CollectionJobOut.model_fields if c != "status"}, "status": job.status.value})


@router.get("/{source_id}", response_model=SourceStatsOut)
def get_source(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    source = _get_source_or_404(db, source_id)
    document_count = db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.source_id == source_id))
    last_run = db.scalar(select(CollectionRun).where(CollectionRun.source_id == source_id).order_by(CollectionRun.started_at.desc()).limit(1))
    data = SourceOut.model_validate(source).model_dump()
    data.pop("access_label", None)
    data["document_count"] = document_count or 0
    data["last_run_status"] = last_run.status if last_run else None
    return SourceStatsOut(**data)


@router.patch("/{source_id}", response_model=SourceOut)
def update_source(
    source_id: uuid.UUID,
    payload: SourceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE)),
):
    source = _get_source_or_404(db, source_id)
    data = payload.model_dump(exclude_unset=True)
    _validate_source_fields(data.get("url", source.url), data.get("source_type", source.source_type), data.get("api_provider", source.api_provider), data.get("config_json", source.config_json))
    before = {k: (getattr(source, k).value if hasattr(getattr(source, k), "value") else getattr(source, k)) for k in data}
    for field, value in data.items():
        setattr(source, field, value)
    if "url" in data and data["url"] != before.get("url"):
        source.access_status, source.access_note, source.consecutive_failures = "unverified", "주소를 바꿨습니다 — 연결 테스트 또는 수집으로 확인하세요", 0  # 주소 변경 이력은 감사 로그에 남는다
    log_action(db, actor_user_id=current_user.id, action="source.update", entity_type="source", entity_id=source.id,
               detail={"before": before, "after": {k: (v.value if hasattr(v, "value") else v) for k, v in data.items()}})
    db.commit()
    db.refresh(source)
    return source


@router.get("/{source_id}/history")
def source_history(source_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(require_roles(*MANAGE))):
    """정보원 설정 변경·비활성화·수집 요청 이력(삭제 대신 비활성화하므로 이력이 보존된다)."""
    _get_source_or_404(db, source_id)
    rows = db.scalars(select(AuditLog).where(AuditLog.entity_type == "source", AuditLog.entity_id == source_id).order_by(AuditLog.created_at.desc()).limit(100)).all()
    out = []
    for r in rows:
        actor = db.get(User, r.actor_user_id) if r.actor_user_id else None
        out.append({"action": r.action, "at": r.created_at.isoformat(), "actor": actor.display_name if actor else "자동 작업", "detail": json.loads(r.detail_json) if r.detail_json else None})
    return out


@router.post("/{source_id}/collect", response_model=CollectStartOut, status_code=status.HTTP_202_ACCEPTED)
def trigger_collection(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*RUN)),
):
    """'지금 수집' — 작업을 만들어 서버가 백그라운드로 처리한다. 진행 상태는 GET /sources/jobs/{job_id} 로 조회한다."""
    source = _get_source_or_404(db, source_id)
    if not source.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="비활성 출처는 수집할 수 없습니다")
    job, created = collection_jobs.enqueue_job(db, source, trigger="manual", user_id=current_user.id)
    if created:
        log_action(db, actor_user_id=current_user.id, action="source.collect", entity_type="source", entity_id=source.id, detail={"job_id": str(job.id)})
        db.commit()
        collection_jobs.start_job_thread(job.id)
    return CollectStartOut(job=_job_out(job), already_running=not created)


@router.get("/{source_id}/jobs", response_model=list[CollectionJobOut])
def list_jobs(source_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _get_source_or_404(db, source_id)
    rows = db.scalars(select(CollectionJob).where(CollectionJob.source_id == source_id).order_by(CollectionJob.created_at.desc()).limit(30)).all()
    return [_job_out(j) for j in rows]


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
    # collected_at으로 정렬하면 한 번의 수집 실행에서 들어온 문서들의 insert 순서가 임의로 보일 수 있어 발표일 기준으로 정렬한다.
    stmt = (
        select(SourceDocument)
        .where(SourceDocument.source_id == source_id)
        .order_by(SourceDocument.published_at.desc().nulls_last(), SourceDocument.collected_at.desc())
    )
    return db.scalars(stmt).all()


# ------------------------------------------------------- 전체 수집 현황 / 일괄 수집 ----

@collection_router.get("/status")
def collection_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """ICT 정보수집 화면 상단 상태: 최근 수집 시각·신규 자료 수·검토할 자료 수·실패 정보원 수·진행 중 작업."""
    now = datetime.now(timezone.utc)
    last_ok = db.scalar(select(func.max(Source.last_successful_collection_at)))
    new_24h = db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.collected_at >= now - timedelta(hours=24), SourceDocument.status.in_([SourceDocumentStatus.COLLECTED, SourceDocumentStatus.UPDATED]))) or 0
    to_review = db.scalar(select(func.count()).select_from(SourceDocument).where(SourceDocument.collected_at >= now - timedelta(days=7), SourceDocument.is_latest.is_(True),
                                                                                   SourceDocument.status.in_([SourceDocumentStatus.COLLECTED, SourceDocumentStatus.UPDATED]))) or 0
    failed = db.scalar(select(func.count()).select_from(Source).where(Source.is_active.is_(True), Source.consecutive_failures > 0)) or 0
    running = db.scalars(select(CollectionJob).where(CollectionJob.status.in_(ACTIVE_JOB_STATUSES))).all()
    return {"last_collected_at": last_ok.isoformat() if last_ok else None, "new_last_24h": new_24h, "to_review": to_review, "failed_sources": failed,
            "active_sources": db.scalar(select(func.count()).select_from(Source).where(Source.is_active.is_(True))) or 0,
            "running_jobs": [{"id": str(j.id), "source_id": str(j.source_id), "status": j.status.value, "stage": j.stage} for j in running]}


@collection_router.post("/run-all", status_code=status.HTTP_202_ACCEPTED)
def run_all(db: Session = Depends(get_db), current_user: User = Depends(require_roles(*RUN))):
    """활성 정보원 전체를 수집 대기열에 넣는다(이미 진행 중인 정보원은 건너뜀)."""
    started, skipped = [], 0
    for s in db.scalars(select(Source).where(Source.is_active.is_(True)).order_by(Source.name)).all():
        job, created = collection_jobs.enqueue_job(db, s, trigger="manual", user_id=current_user.id)
        if created:
            started.append(job.id)
        else:
            skipped += 1
    log_action(db, actor_user_id=current_user.id, action="source.collect_all", entity_type="source", entity_id=uuid.uuid4(), detail={"started": len(started), "skipped": skipped})
    db.commit()
    # 대량 작업은 서버가 순서대로 처리한다(정보원별 동시 실행 없음)
    import threading
    from app.core.db import SessionLocal
    import os
    if started and not os.environ.get("PYTEST_CURRENT_TEST"):
        def _seq() -> None:
            for jid in started:
                collection_jobs.execute_job(SessionLocal, jid)
        threading.Thread(target=_seq, daemon=True, name="collect-all").start()
    return {"started": len(started), "already_running": skipped}
