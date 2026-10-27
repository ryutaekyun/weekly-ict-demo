"""수집 작업(Job) 큐·실행·복구·예약 — '지금 수집' 버튼과 자동 수집이 같은 경로를 쓴다.

- 작업은 DB(collection_jobs)에 기록되고 화면을 닫아도 서버가 끝까지 처리한다. 상태·진행 단계·건수는 작업 ID 로 조회한다.
- 같은 정보원의 진행 중 작업은 1건만 허용한다(active_key 유니크). 연속 클릭하면 기존 작업을 돌려준다.
- 실행은 queued→running 을 UPDATE 한 쪽만 가져간다(API 스레드·별도 작업자가 동시에 있어도 중복 실행 없음).
- 서버가 도중에 멈추면 heartbeat 가 끊긴 running 작업을 'interrupted'(실패 상태)로 정리한다.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import log_action
from app.core.config import settings
from app.models.collection_job import CollectionJob
from app.models.collection_run import CollectionRun
from app.models.enums import ACTIVE_JOB_STATUSES, ClassificationRelevance, ClusterReviewStatus, CollectionJobStatus, CollectionRunStatus, UserRole
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User

log = logging.getLogger("collector")
FULL_PIPELINE_PER_JOB = 8  # 전문 추출까지 처리하는 신규 문서 수(나머지는 제목·초록 기준 자동 분류)
CLUSTER_ANALYSIS_PER_JOB = 15


class JobCancelled(Exception):
    pass


class JobTimeout(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ------------------------------------------------------------------ 큐 ----

def active_job_for(db: Session, source_id) -> CollectionJob | None:
    return db.scalar(select(CollectionJob).where(CollectionJob.source_id == source_id, CollectionJob.status.in_(ACTIVE_JOB_STATUSES)))


def enqueue_job(db: Session, source: Source, *, trigger: str, user_id=None) -> tuple[CollectionJob, bool]:
    """(작업, 새로 만들었는지). 이미 진행 중이면 그 작업을 그대로 돌려준다."""
    existing = active_job_for(db, source.id)
    if existing is not None:
        return existing, False
    job = CollectionJob(source_id=source.id, status=CollectionJobStatus.QUEUED, trigger=trigger, requested_by_user_id=user_id, active_key=str(source.id), stage="대기 중")
    db.add(job)
    try:
        db.commit()
    except IntegrityError:  # 동시에 다른 요청이 먼저 만들었다
        db.rollback()
        return active_job_for(db, source.id), False  # type: ignore[return-value]
    db.refresh(job)
    return job, True


def claim_job(db: Session, job_id) -> bool:
    res = db.execute(update(CollectionJob).where(CollectionJob.id == job_id, CollectionJob.status == CollectionJobStatus.QUEUED)
                     .values(status=CollectionJobStatus.RUNNING, started_at=_now(), heartbeat_at=_now(), stage="연결 중"))
    db.commit()
    return res.rowcount == 1


def recover_stale_jobs(db: Session) -> int:
    """heartbeat 가 끊긴 running 작업을 interrupted 로 정리해 정보원이 다시 수집될 수 있게 한다."""
    limit = _now() - timedelta(seconds=settings.collector_stale_job_seconds)
    n = 0
    for job in db.scalars(select(CollectionJob).where(CollectionJob.status == CollectionJobStatus.RUNNING)).all():
        hb = _aware(job.heartbeat_at) or _aware(job.started_at) or _aware(job.created_at)
        if hb is not None and hb < limit:
            job.status = CollectionJobStatus.INTERRUPTED
            job.active_key = None
            job.finished_at = _now()
            job.error_type = "interrupted"
            job.error_message = "서버·작업자가 중단되어 끝까지 처리하지 못했습니다. 다시 수집하세요."
            n += 1
    if n:
        db.commit()
    return n


def request_cancel(db: Session, job: CollectionJob) -> CollectionJob:
    if job.status == CollectionJobStatus.QUEUED:
        job.status = CollectionJobStatus.CANCELLED
        job.active_key = None
        job.finished_at = _now()
    elif job.status == CollectionJobStatus.RUNNING:
        job.cancel_requested = True
    db.commit()
    return job


# ------------------------------------------------------------------ 실행 ----

def _finish(db: Session, job: CollectionJob, status: CollectionJobStatus, *, error_type: str | None = None, error: str | None = None) -> None:
    job.status = status
    job.active_key = None
    job.finished_at = _now()
    job.heartbeat_at = _now()
    job.error_type = error_type
    job.error_message = (error or None) and error[:2000]
    job.cancel_requested = job.cancel_requested and status == CollectionJobStatus.CANCELLED
    db.commit()


def _admin_user_id(db: Session, job: CollectionJob):
    if job.requested_by_user_id:
        return job.requested_by_user_id
    return db.scalar(select(User.id).where(User.role == UserRole.ADMIN, User.is_active.is_(True), User.approval_status == "approved").limit(1))


def _post_process(db: Session, job: CollectionJob, source: Source, ingest) -> None:
    """수집 직후 후처리: ICT 분야 자동 분류 → 이슈 연결 → 원문 수정 시 재검토 표시."""
    from app.models.document_classification import DocumentClassification
    from app.services.classification import run_classification
    from app.services.issue_pipeline import run_analysis_and_recommendation_for_cluster, run_clustering_for_document
    from app.services.pipeline import run_full_pipeline

    uid = _admin_user_id(db, job)
    clusters: dict = {}
    job.stage = "분야 자동 분류"
    db.commit()
    for i, doc_id in enumerate(ingest.new_ids):
        doc = db.get(SourceDocument, doc_id)
        if doc is None:
            continue
        try:
            if i < FULL_PIPELINE_PER_JOB:
                run_full_pipeline(db, doc, source, prefer_ai=False)  # 전문 추출·분류·가치평가(규칙 기반, 외부 AI 호출 없음)
            else:
                run_classification(db, doc, text=f"{doc.title}\n\n{doc.raw_text or ''}".strip(), prefer_ai=False)
                db.commit()
            job.items_classified += 1
            cls = db.scalar(select(DocumentClassification).where(DocumentClassification.document_id == doc.id))
            if cls is not None and cls.relevance == ClassificationRelevance.MATCHED and uid is not None:
                c = run_clustering_for_document(db, doc, actor_user_id=uid)
                clusters[c.id] = c
        except Exception as exc:  # noqa: BLE001 - 한 건의 후처리 실패가 작업 전체를 실패시키지 않는다
            db.rollback()
            log.warning("post-process failed for %s: %s", doc_id, exc)
        job.heartbeat_at = _now()
        db.commit()

    job.stage = "이슈 분석·후보 추천"
    db.commit()
    for c in list(clusters.values())[:CLUSTER_ANALYSIS_PER_JOB]:
        try:
            run_analysis_and_recommendation_for_cluster(db, c, created_by_user_id=uid, prefer_ai=False)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            log.warning("cluster analysis failed for %s: %s", c.id, exc)

    # 원문 수정: 기존 문서가 속한 이슈를 재검토 대상으로 표시하고 변경 이력을 감사 로그에 남긴다
    for old, new in ingest.versioned:
        for m in db.scalars(select(IssueClusterDocument).where(IssueClusterDocument.document_id == old.id)).all():
            cl = db.get(IssueCluster, m.issue_cluster_id)
            if cl is not None:
                cl.review_status = ClusterReviewStatus.NEEDS_REVIEW
        log_action(db, actor_user_id=None, action="document.version", entity_type="source_document", entity_id=new.id,
                   detail={"previous_version_id": str(old.id), "version_no": new.version_no, "origin_url": new.origin_url})
    db.commit()


def execute_job(session_factory: Callable[[], Session], job_id) -> None:
    from app.services.collection import run_collection

    db = session_factory()
    try:
        if not claim_job(db, job_id):
            return  # 다른 실행기가 이미 가져갔거나 취소됨
        job = db.get(CollectionJob, job_id)
        source = db.get(Source, job.source_id)
        started = _now()

        def progress(done: int, res) -> None:
            job.items_found, job.items_new, job.items_duplicate, job.items_updated, job.items_failed = res.found, res.new, res.duplicate, res.updated, res.failed
            job.stage = f"저장 중 ({done}/{res.found})"
            job.heartbeat_at = _now()
            db.commit()
            db.refresh(job)
            if job.cancel_requested:
                raise JobCancelled()
            if (_now() - started).total_seconds() > settings.collector_job_timeout_seconds:
                raise JobTimeout()

        try:
            job.stage = "공식 주소에 연결하는 중"
            db.commit()
            run = run_collection(db, source, on_progress=progress)
            job.run_id = run.id
            if run.status == CollectionRunStatus.FAILED:
                et = run.error_type.value if run.error_type else "error"
                _finish(db, job, CollectionJobStatus.FAILED, error_type=et, error=run.error_message)
                return
            ingest = getattr(run, "_ingest", None)
            if ingest is not None:
                job.items_found, job.items_new, job.items_duplicate, job.items_updated, job.items_failed = ingest.found, ingest.new, ingest.duplicate, ingest.updated, ingest.failed
                db.commit()
                _post_process(db, job, source, ingest)
            _finish(db, job, CollectionJobStatus.SUCCEEDED)
        except JobCancelled:
            db.rollback()
            job = db.get(CollectionJob, job_id)
            _finish(db, job, CollectionJobStatus.CANCELLED, error_type="cancelled", error="사용자가 취소했습니다")
        except JobTimeout:
            db.rollback()
            job = db.get(CollectionJob, job_id)
            _finish(db, job, CollectionJobStatus.TIMEOUT, error_type="timeout", error=f"{settings.collector_job_timeout_seconds}초를 넘어 중단했습니다")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            job = db.get(CollectionJob, job_id)
            _finish(db, job, CollectionJobStatus.FAILED, error_type="exception", error=f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def start_job_thread(job_id) -> None:
    """API 프로세스 안에서 작업을 바로 시작한다(작업자 프로세스가 없어도 '지금 수집'이 동작하도록). 테스트 중에는 시작하지 않는다."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    from app.core.db import SessionLocal

    threading.Thread(target=execute_job, args=(SessionLocal, job_id), daemon=True, name=f"collect-{job_id}").start()


# ------------------------------------------------------------------ 예약 ----

def is_due(source: Source, now: datetime) -> bool:
    if not source.is_active or (source.interval_minutes or 0) <= 0:
        return False
    last = _aware(source.last_attempted_at)
    if last is None:
        return True
    interval = timedelta(minutes=source.interval_minutes)
    if source.consecutive_failures > 0:  # 실패 후에는 길게 기다리지 않고 짧게 재시도(최대 주기까지 점점 늘림)
        interval = min(interval, timedelta(minutes=15 * (2 ** min(source.consecutive_failures - 1, 4))))
    return now >= last + interval


def schedule_tick(session_factory: Callable[[], Session], only_source_ids: set[str] | None = None) -> dict:
    """한 번의 예약 점검: 멈춘 작업 정리 → 주기가 지난 정보원 작업 등록 → 대기 작업을 순서대로 실행."""
    db = session_factory()
    ran, enqueued = [], 0
    try:
        from app.services.collection import backfill_document_keys
        backfill_document_keys(db)
        recovered = recover_stale_jobs(db)
        now = _now()
        for s in db.scalars(select(Source).where(Source.is_active.is_(True))).all():
            if only_source_ids is not None and str(s.id) not in only_source_ids:
                continue
            if is_due(s, now):
                _, created = enqueue_job(db, s, trigger="schedule")
                enqueued += 1 if created else 0
        q = select(CollectionJob).where(CollectionJob.status == CollectionJobStatus.QUEUED).order_by(CollectionJob.created_at)
        queued = [j for j in db.scalars(q).all() if only_source_ids is None or str(j.source_id) in only_source_ids]
        ids = [j.id for j in queued]
    finally:
        db.close()
    for jid in ids:
        execute_job(session_factory, jid)
        ran.append(str(jid))
    return {"recovered": recovered, "enqueued": enqueued, "ran": ran}
