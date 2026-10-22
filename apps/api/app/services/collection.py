"""다방식(API/RSS/HTML) 출처 수집 엔진.

설계 원칙(진행 원칙 준수):
- 실제로 존재가 확인된 출처 URL만 사용한다 — URL을 추측하거나 생성하지 않는다.
- 수집한 원문의 origin_url/content_hash를 보존해 중복 기사 감지와 출처 추적을 가능하게 한다.
- 수집 실패는 삼키지 않고 collection_runs에 상태·오류 유형·메시지·재시도 횟수로 기록한다.
- 수집 실패가 반복돼도 출처를 자동으로 비활성화하지 않는다 — needs_review만 표시해 관리자 확인을 기다린다.
- 요청 User-Agent에 봇 식별 정보를 명시해 발신처를 투명하게 밝힌다(로봇 배제 정책 존중).
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.collection_run import CollectionRun
from app.models.enums import CollectionErrorType, CollectionRunStatus, DocumentType, SourceDocumentStatus
from app.models.source import Source
from app.models.source_document import SourceDocument

USER_AGENT = "TNP-AI-Platform-Collector/0.1 (ICT research collection; contact: platform-admin@tenopa.co.kr)"
FETCH_TIMEOUT_SECONDS = 15.0
MAX_ITEMS_PER_RUN = 50
CONSECUTIVE_FAILURES_BEFORE_REVIEW = 3


@dataclass
class NormalizedEntry:
    title: str
    link: str
    published_at: datetime | None
    summary: str | None
    document_type: DocumentType = DocumentType.OTHER
    is_peer_reviewed: bool | None = None
    attachment_url: str | None = None


def _content_hash(title: str, link: str) -> str:
    normalized = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def classify_http_error(exc: Exception) -> CollectionErrorType:
    if isinstance(exc, httpx.TimeoutException):
        return CollectionErrorType.TIMEOUT
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 429:
            return CollectionErrorType.HTTP_429
        if 500 <= code < 600:
            return CollectionErrorType.HTTP_5XX
        return CollectionErrorType.HTTP_4XX
    if isinstance(exc, httpx.HTTPError):
        return CollectionErrorType.CONNECTION_ERROR
    return CollectionErrorType.PARSE_ERROR


# ---------------------------------------------------------------- RSS ----

def fetch_raw_feed(url: str) -> bytes:
    with _http_client() as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content


def _fetch_rss_entries(source: Source) -> list[NormalizedEntry]:
    raw = fetch_raw_feed(source.url)
    parsed = feedparser.parse(raw)
    entries: list[NormalizedEntry] = []
    for entry in parsed.entries[:MAX_ITEMS_PER_RUN]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        published = _parse_rfc822(entry.get("published")) or _parse_rfc822(entry.get("updated"))
        is_arxiv = "arxiv.org" in source.url
        entries.append(
            NormalizedEntry(
                title=title,
                link=link,
                published_at=published,
                summary=entry.get("summary") or None,
                document_type=DocumentType.PAPER if is_arxiv else DocumentType.PRESS_RELEASE,
                is_peer_reviewed=False if is_arxiv else None,  # arXiv는 프리프린트 — 동료심사 전
            )
        )
    return entries


# ----------------------------------------------------- API: Federal Register ----

def _fetch_federal_register_entries(source: Source) -> list[NormalizedEntry]:
    """federalregister.gov의 공개 REST API(JSON) — 미국 연방 규정·고시 1차 출처.

    source.url에는 이미 기관/검색어로 필터링된 구체적인 쿼리 문자열이 들어있다
    (예: ?conditions[agencies][]=...&conditions[term]=...). API 키가 필요 없다.
    """
    with _http_client() as client:
        response = client.get(source.url)
        response.raise_for_status()
        data = response.json()

    results = data.get("results", [])[:MAX_ITEMS_PER_RUN]
    entries: list[NormalizedEntry] = []
    type_map = {
        "RULE": DocumentType.LAW,
        "PROPOSED RULE": DocumentType.LAW,
        "NOTICE": DocumentType.POLICY,
        "PRESIDENTIAL DOCUMENT": DocumentType.POLICY,
    }
    for item in results:
        title = (item.get("title") or "").strip()
        link = (item.get("html_url") or "").strip()
        if not title or not link:
            continue
        published_at = None
        if item.get("publication_date"):
            try:
                published_at = datetime.strptime(item["publication_date"], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                published_at = None
        entries.append(
            NormalizedEntry(
                title=title,
                link=link,
                published_at=published_at,
                summary=item.get("abstract"),
                document_type=type_map.get((item.get("type") or "").upper(), DocumentType.POLICY),
                attachment_url=item.get("pdf_url"),
            )
        )
    return entries


API_PROVIDERS = {
    "federal_register": _fetch_federal_register_entries,
}


def _fetch_entries(source: Source) -> list[NormalizedEntry]:
    if source.source_type.value == "rss":
        return _fetch_rss_entries(source)
    if source.source_type.value == "api":
        handler = API_PROVIDERS.get(source.api_provider or "")
        if handler is None:
            raise ValueError(f"등록되지 않은 api_provider입니다: {source.api_provider!r}")
        return handler(source)
    raise ValueError(f"아직 구현되지 않은 수집 방식입니다: {source.source_type!r}")


# --------------------------------------------------------- 공통 실행 로직 ----

def run_collection(db: Session, source: Source) -> CollectionRun:
    now = datetime.now(timezone.utc)
    run = CollectionRun(
        source_id=source.id,
        started_at=now,
        status=CollectionRunStatus.FAILED,  # 아래에서 성공 시 덮어씀
    )
    db.add(run)
    db.flush()

    source.last_attempted_at = now

    try:
        entries = _fetch_entries(source)
    except Exception as exc:  # noqa: BLE001 - 실패 유형을 분류해 그대로 기록하기 위해 넓게 잡는다
        run.status = CollectionRunStatus.FAILED
        run.error_type = classify_http_error(exc)
        run.error_message = f"{type(exc).__name__}: {exc}"
        run.finished_at = datetime.now(timezone.utc)
        run.retry_count += 1

        source.consecutive_failures += 1
        if source.consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_REVIEW:
            source.needs_review = True

        db.commit()
        db.refresh(run)
        return run

    if not entries:
        run.status = CollectionRunStatus.SUCCESS
        run.items_found = 0
        run.finished_at = datetime.now(timezone.utc)
        source.consecutive_failures = 0
        source.last_successful_collection_at = now
        db.commit()
        db.refresh(run)
        return run

    items_new = 0
    items_duplicate = 0
    items_updated = 0

    for entry in entries:
        content_hash = _text_hash(f"{entry.title}|{entry.summary or ''}")

        existing_same_url = db.scalar(
            select(SourceDocument)
            .where(SourceDocument.origin_url == entry.link)
            .order_by(SourceDocument.collected_at.desc())
        )

        if existing_same_url is not None and existing_same_url.content_hash == content_hash:
            # 완전히 동일한 URL+내용 — 진짜 중복이므로 새 행을 만들지 않는다
            items_duplicate += 1
            continue

        existing_same_content_elsewhere = db.scalar(
            select(SourceDocument).where(SourceDocument.content_hash == content_hash)
        )

        doc = SourceDocument(
            source_id=source.id,
            collection_run_id=run.id,
            title=entry.title,
            origin_url=entry.link,
            attachment_url=entry.attachment_url,
            published_at=entry.published_at,
            collected_at=datetime.now(timezone.utc),
            raw_text=entry.summary,
            content_hash=content_hash,
            country_code=source.country_code,
            field_code=source.field_code,  # Phase 2-2에서 자동분류로 대체 예정 — 지금은 출처 분야를 그대로 사용
            collection_method=source.source_type,
            document_type=entry.document_type,
            is_peer_reviewed=entry.is_peer_reviewed,
            requires_primary_source_check=(
                entry.document_type == DocumentType.NEWS and not source.is_primary_source
            ),
        )

        if existing_same_url is not None:
            # 같은 URL인데 내용이 달라졌다 — 새 버전으로 기록(진짜 중복과는 다른 개념)
            doc.status = SourceDocumentStatus.UPDATED
            doc.previous_version_id = existing_same_url.id
            items_updated += 1
        elif existing_same_content_elsewhere is not None:
            doc.status = SourceDocumentStatus.DUPLICATE
            doc.duplicate_of_id = existing_same_content_elsewhere.id
            items_duplicate += 1
        else:
            doc.status = SourceDocumentStatus.COLLECTED
            items_new += 1

        db.add(doc)

    run.items_found = len(entries)
    run.items_new = items_new
    run.items_duplicate = items_duplicate
    run.items_updated = items_updated
    run.status = CollectionRunStatus.SUCCESS
    run.finished_at = datetime.now(timezone.utc)

    source.consecutive_failures = 0
    source.needs_review = False
    source.last_successful_collection_at = now

    db.commit()
    db.refresh(run)
    return run
