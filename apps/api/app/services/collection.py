"""RSS 기반 출처 수집 엔진.

설계 원칙(진행 원칙 준수):
- 실제로 존재가 확인된 출처 URL만 사용한다 — URL을 추측하거나 생성하지 않는다.
- 수집한 원문의 origin_url/content_hash를 보존해 중복 기사 감지와 출처 추적을 가능하게 한다.
- 수집 실패는 삼키지 않고 collection_runs에 상태·오류 메시지·재시도 횟수로 기록한다.
- 요청 User-Agent에 봇 식별 정보를 명시해 발신처를 투명하게 밝힌다(로봇 배제 정책 존중).
"""

import hashlib
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection_run import CollectionRun
from app.models.enums import CollectionRunStatus, SourceDocumentStatus
from app.models.source import Source
from app.models.source_document import SourceDocument

USER_AGENT = "TNP-AI-Platform-Collector/0.1 (ICT research collection; contact: platform-admin@tenopa.co.kr)"
FETCH_TIMEOUT_SECONDS = 15.0
MAX_ITEMS_PER_RUN = 50


def _content_hash(title: str, link: str) -> str:
    normalized = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _parse_published(entry) -> datetime | None:
    for key in ("published", "updated"):
        value = entry.get(key)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            continue
    return None


def fetch_raw_feed(url: str) -> bytes:
    with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def run_collection(db: Session, source: Source) -> CollectionRun:
    run = CollectionRun(
        source_id=source.id,
        started_at=datetime.now(timezone.utc),
        status=CollectionRunStatus.FAILED,  # 아래에서 성공 시 덮어씀
    )
    db.add(run)
    db.flush()

    try:
        raw = fetch_raw_feed(source.url)
    except httpx.HTTPError as exc:
        run.status = CollectionRunStatus.FAILED
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        run.retry_count += 1
        db.commit()
        db.refresh(run)
        return run

    parsed = feedparser.parse(raw)
    entries = parsed.entries[:MAX_ITEMS_PER_RUN]

    items_new = 0
    items_duplicate = 0

    for entry in entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue

        existing_by_url = db.scalar(select(SourceDocument).where(SourceDocument.origin_url == link))
        if existing_by_url is not None:
            items_duplicate += 1
            continue

        content_hash = _content_hash(title, link)
        existing_by_hash = db.scalar(
            select(SourceDocument).where(SourceDocument.content_hash == content_hash)
        )

        doc = SourceDocument(
            source_id=source.id,
            collection_run_id=run.id,
            title=title,
            origin_url=link,
            published_at=_parse_published(entry),
            collected_at=datetime.now(timezone.utc),
            raw_text=(entry.get("summary") or None),
            content_hash=content_hash,
            status=SourceDocumentStatus.DUPLICATE if existing_by_hash else SourceDocumentStatus.COLLECTED,
            duplicate_of_id=existing_by_hash.id if existing_by_hash else None,
        )
        db.add(doc)

        if existing_by_hash:
            items_duplicate += 1
        else:
            items_new += 1

    run.items_found = len(entries)
    run.items_new = items_new
    run.items_duplicate = items_duplicate
    run.status = CollectionRunStatus.SUCCESS if entries or parsed.bozo == 0 else CollectionRunStatus.PARTIAL
    run.finished_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(run)
    return run
