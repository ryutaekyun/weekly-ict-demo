"""다방식(REST API·RSS/Atom·HTML 목록·PDF·메타데이터 전용) 정보원 수집 엔진.

설계 원칙:
- 실제로 존재가 확인된 출처 URL만 사용한다 — URL을 추측하거나 생성하지 않는다.
- 공식 API/RSS 를 우선하고, 비공식 크롤링으로 우회하지 않는다. robots.txt·요청 간격·응답 크기·내부망 차단을 지킨다(url_guard).
- 원문의 origin_url/content_hash/외부 고유ID 를 보존해 중복 감지와 출처 추적을 가능하게 한다.
- 같은 문서가 수정되면 기존 행을 덮어쓰지 않고 새 버전 행(previous_version_id, version_no)을 쌓고 최신본만 is_latest 로 표시한다.
- 실패는 삼키지 않고 collection_runs / collection_jobs 에 유형·메시지로 기록한다. 반복 실패해도 자동 비활성화하지 않는다.
- 발표일(published_at)·수정일(document_updated_at)·수집일(collected_at)은 서로 다른 필드로 보존한다.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import feedparser
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.collection_run import CollectionRun
from app.models.enums import CollectionErrorType, CollectionRunStatus, DocumentType, SourceDocumentStatus, SourceType
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import url_guard

USER_AGENT = "TNP-AI-Platform-Collector/0.2 (ICT research collection; contact: platform-admin@tenopa.co.kr)"
FETCH_TIMEOUT_SECONDS = 15.0
MAX_ITEMS_PER_RUN = 50
CONSECUTIVE_FAILURES_BEFORE_REVIEW = 3

# 정보원 접속 상태 라벨(화면 표시용)
ACCESS_LABELS = {
    "ok": "정상 수집", "metadata_only": "메타데이터만 수집", "blocked": "접속 제한", "moved": "주소 변경",
    "unverified": "미검증", "error": "일시 오류",
}


@dataclass
class NormalizedEntry:
    title: str
    link: str
    published_at: datetime | None
    summary: str | None
    document_type: DocumentType = DocumentType.OTHER
    is_peer_reviewed: bool | None = None
    attachment_url: str | None = None
    external_id: str | None = None  # 공식 문서번호·arXiv ID 등
    updated_at: datetime | None = None  # 원문 수정일(발표일과 별개)
    language: str | None = None


@dataclass
class IngestResult:
    found: int = 0
    new: int = 0
    duplicate: int = 0
    updated: int = 0
    failed: int = 0
    new_ids: list = field(default_factory=list)
    versioned: list = field(default_factory=list)  # (이전 문서, 새 문서)


# ---------------------------------------------------------------- 공통 유틸 ----

def _content_hash(title: str, link: str) -> str:
    normalized = f"{title.strip().lower()}|{link.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|source$)", re.I)


def normalize_url(url: str) -> str:
    """중복 판별용 정규화: 호스트 소문자, http→https, 조각(#) 제거, 추적 파라미터 제거, 끝 슬래시 정리."""
    p = urlparse(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)])
    path = p.path.rstrip("/") or "/"
    return urlunparse(("https" if p.scheme in ("http", "https") else p.scheme, p.netloc.lower(), path, "", query, ""))


def detect_language(text: str) -> str:
    """제목·초록 기준 간이 언어 판별(ko/ja/zh/en/und) — 번역 단계에서 번역 모델을 고르는 데 쓴다."""
    sample = (text or "")[:600]
    if not sample.strip():
        return "und"
    hangul = sum(1 for c in sample if "가" <= c <= "힣")
    kana = sum(1 for c in sample if "぀" <= c <= "ヿ")
    han = sum(1 for c in sample if "一" <= c <= "鿿")
    n = max(len(sample), 1)
    if hangul / n > 0.1:
        return "ko"
    if kana / n > 0.05:
        return "ja"
    if han / n > 0.1:
        return "zh"
    return "en"


def _http_client() -> httpx.Client:
    return url_guard.guarded_client(USER_AGENT, FETCH_TIMEOUT_SECONDS)


def classify_http_error(exc: Exception) -> CollectionErrorType:
    if isinstance(exc, url_guard.UnsafeURLError):
        return CollectionErrorType.BLOCKED_URL
    if isinstance(exc, url_guard.ResponseTooLargeError):
        return CollectionErrorType.TOO_LARGE
    if isinstance(exc, url_guard.RobotsDisallowedError):
        return CollectionErrorType.ROBOTS_DISALLOWED
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


def access_status_for(error_type: CollectionErrorType | None, exc: Exception | None = None) -> tuple[str, str]:
    """수집 실패 유형 → (접속 상태, 사람이 읽는 설명). 접속 제한을 우회하지 않고 사유만 정확히 표시한다."""
    if error_type is None:
        return "ok", "정상 수집"
    if error_type == CollectionErrorType.ROBOTS_DISALLOWED:
        return "blocked", "robots.txt 가 이 주소의 자동 수집을 허용하지 않습니다 — 우회하지 않았습니다. 공식 API·RSS 가 있는지 확인하세요."
    if error_type in (CollectionErrorType.HTTP_429, CollectionErrorType.BLOCKED_URL):
        return "blocked", ("요청 한도 초과(429) — 수집 간격을 늘리세요." if error_type == CollectionErrorType.HTTP_429 else f"안전 규칙에 막힌 주소입니다: {exc}")
    if error_type == CollectionErrorType.HTTP_4XX:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        if code in (401, 403):
            return "blocked", f"서버가 접근을 거부했습니다(HTTP {code}) — 우회하지 않았습니다. 허용된 공식 API·RSS 경로가 있는지 확인하세요."
        if code in (404, 410):
            return "moved", f"주소를 찾을 수 없습니다(HTTP {code}) — 공식 주소가 바뀌었는지 확인하세요."
        return "error", f"HTTP {code} 오류"
    if error_type == CollectionErrorType.PARSE_ERROR:
        return "error", "응답을 해석하지 못했습니다(형식 변경 가능성)."
    if error_type == CollectionErrorType.TOO_LARGE:
        return "error", "응답이 허용 크기를 넘었습니다."
    return "error", "일시적인 접속 오류입니다(시간 초과·연결 실패·서버 오류) — 다시 시도하세요."


def fetch_raw_feed(url: str) -> bytes:
    with _http_client() as client:
        response = client.get(url)
        response.raise_for_status()
        return url_guard.check_size(response.content)


def _source_config(source: Source) -> dict:
    try:
        cfg = json.loads(source.config_json) if source.config_json else {}
        return cfg if isinstance(cfg, dict) else {}
    except ValueError:
        return {}


def _check_robots(source: Source, url: str) -> None:
    if source.respect_robots and not url_guard.robots_allowed(url, USER_AGENT):
        raise url_guard.RobotsDisallowedError(f"robots.txt 가 {url} 수집을 허용하지 않습니다")


# ---------------------------------------------------------------- RSS / Atom ----

def _entry_dt(entry, key: str) -> datetime | None:
    parsed = entry.get(f"{key}_parsed")
    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pass
    return _parse_rfc822(entry.get(key)) or _parse_iso(entry.get(key))


def _fetch_rss_entries(source: Source) -> list[NormalizedEntry]:
    _check_robots(source, source.url)
    raw = fetch_raw_feed(source.url)
    parsed = feedparser.parse(raw)
    metadata_only = source.source_type == SourceType.METADATA
    entries: list[NormalizedEntry] = []
    for entry in parsed.entries[:MAX_ITEMS_PER_RUN]:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        is_arxiv = "arxiv.org" in source.url
        summary = None if metadata_only else (entry.get("summary") or None)
        entries.append(
            NormalizedEntry(
                title=title,
                link=link,
                published_at=_entry_dt(entry, "published") or _entry_dt(entry, "updated"),
                updated_at=_entry_dt(entry, "updated"),
                summary=summary,
                document_type=DocumentType.PAPER if is_arxiv else DocumentType.PRESS_RELEASE,
                is_peer_reviewed=False if is_arxiv else None,  # arXiv는 프리프린트 — 동료심사 전
                external_id=(entry.get("id") or entry.get("guid") or None),
            )
        )
    return entries


# ----------------------------------------------------- API: Federal Register ----

def _fetch_federal_register_entries(source: Source) -> list[NormalizedEntry]:
    """federalregister.gov의 공개 REST API(JSON) — 미국 연방 규정·고시 1차 출처. API 키가 필요 없다."""
    with _http_client() as client:
        response = client.get(source.url)
        response.raise_for_status()
        url_guard.check_size(getattr(response, "content", b""))
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
                published_at = datetime.strptime(item["publication_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
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
                external_id=item.get("document_number"),
            )
        )
    return entries


# ----------------------------------------------------------- API: arXiv ----

_ARXIV_ID = re.compile(r"arxiv\.org/abs/([^v?#]+(?:/[^v?#]+)?)(v\d+)?", re.I)


def _fetch_arxiv_api_entries(source: Source) -> list[NormalizedEntry]:
    """arXiv 공식 API(Atom). 호출 빈도 안내(3초 간격)를 지키며, 논문 ID(버전 제외)를 문서 고유 ID로 쓴다."""
    raw = fetch_raw_feed(source.url)
    parsed = feedparser.parse(raw)
    entries: list[NormalizedEntry] = []
    for e in parsed.entries[:MAX_ITEMS_PER_RUN]:
        title = re.sub(r"\s+", " ", (e.get("title") or "")).strip()
        link = (e.get("link") or e.get("id") or "").strip()
        m = _ARXIV_ID.search(link or "")
        if not title or not m:
            continue
        arxiv_id = m.group(1)
        entries.append(
            NormalizedEntry(
                title=title,
                link=f"https://arxiv.org/abs/{arxiv_id}",
                published_at=_entry_dt(e, "published"),
                updated_at=_entry_dt(e, "updated"),
                summary=re.sub(r"\s+", " ", e.get("summary") or "").strip() or None,
                document_type=DocumentType.PAPER,
                is_peer_reviewed=False,
                external_id=f"arxiv:{arxiv_id}",
                attachment_url=f"https://arxiv.org/pdf/{arxiv_id}",
            )
        )
    return entries


# ------------------------------------------------------------- HTML / PDF ----

def _fetch_html_entries(source: Source) -> list[NormalizedEntry]:
    """공개 HTML 목록 페이지에서 링크를 수집한다(허용된 곳만). 설정: {"link_pattern": "정규식", "max_items": 30}."""
    _check_robots(source, source.url)
    cfg = _source_config(source)
    pattern = re.compile(cfg["link_pattern"]) if cfg.get("link_pattern") else None
    with _http_client() as client:
        response = client.get(source.url)
        response.raise_for_status()
        html = url_guard.check_size(response.content)
    soup = BeautifulSoup(html, "html.parser")  # 스크립트는 실행하지 않고 텍스트·링크만 읽는다
    seen: set[str] = set()
    entries: list[NormalizedEntry] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(source.url, a["href"].strip())
        text = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        if not href.startswith(("http://", "https://")) or len(text) < 8 or href in seen:
            continue
        if pattern and not pattern.search(href):
            continue
        if not pattern and urlparse(href).netloc != urlparse(source.url).netloc:
            continue
        seen.add(href)
        entries.append(NormalizedEntry(title=text[:500], link=href, published_at=None, summary=None, document_type=DocumentType.OTHER))
        if len(entries) >= int(cfg.get("max_items", 30)):
            break
    return entries


def _fetch_pdf_entries(source: Source) -> list[NormalizedEntry]:
    """공식 PDF 1건 — 제목(설정 title)·URL 과 파일 내용 해시만 보존한다(원문 변경 감지)."""
    _check_robots(source, source.url)
    cfg = _source_config(source)
    with _http_client() as client:
        response = client.get(source.url)
        response.raise_for_status()
        body = url_guard.check_size(response.content)
    if not body.startswith(b"%PDF"):
        raise ValueError("PDF 형식이 아닙니다(응답이 %PDF 로 시작하지 않음)")
    digest = hashlib.sha256(body).hexdigest()
    title = cfg.get("title") or urlparse(source.url).path.rsplit("/", 1)[-1] or source.name
    return [NormalizedEntry(title=str(title)[:500], link=source.url, published_at=None, summary=f"PDF 파일 해시 {digest}", document_type=DocumentType.OTHER, attachment_url=source.url)]


API_PROVIDERS = {
    "federal_register": _fetch_federal_register_entries,
    "arxiv_api": _fetch_arxiv_api_entries,
}


def _fetch_entries(source: Source) -> list[NormalizedEntry]:
    st = source.source_type
    if st in (SourceType.RSS, SourceType.METADATA):
        return _fetch_rss_entries(source)
    if st == SourceType.API:
        handler = API_PROVIDERS.get(source.api_provider or "")
        if handler is None:
            raise ValueError(f"등록되지 않은 api_provider입니다: {source.api_provider!r}")
        return handler(source)
    if st == SourceType.HTML:
        return _fetch_html_entries(source)
    if st == SourceType.PDF:
        return _fetch_pdf_entries(source)
    raise ValueError(f"아직 구현되지 않은 수집 방식입니다: {source.source_type!r}")


def fetch_preview(source_like: Source) -> list[NormalizedEntry]:
    """연결 테스트 — DB에 저장하지 않고 실제로 접속해 파싱 가능한 항목 목록만 돌려준다."""
    url_guard.set_host_interval(urlparse(source_like.url).hostname or "", source_like.min_request_interval_seconds)
    return _fetch_entries(source_like)


# --------------------------------------------------------- 저장·중복·버전 ----

def _find_existing(db: Session, source: Source, entry: NormalizedEntry, norm: str) -> SourceDocument | None:
    conds = [SourceDocument.origin_url == entry.link, SourceDocument.normalized_url == norm]
    stmt = select(SourceDocument).where(SourceDocument.source_id == source.id, or_(*conds))
    if entry.external_id:
        stmt = select(SourceDocument).where(SourceDocument.source_id == source.id, or_(SourceDocument.external_id == entry.external_id, *conds))
    return db.scalar(stmt.order_by(SourceDocument.is_latest.desc(), SourceDocument.version_no.desc(), SourceDocument.collected_at.desc()))


def ingest_entries(
    db: Session, source: Source, entries: list[NormalizedEntry], run: CollectionRun, *,
    on_progress: Callable[[int, IngestResult], None] | None = None,
) -> IngestResult:
    res = IngestResult(found=len(entries))
    metadata_only = source.source_type == SourceType.METADATA
    for idx, entry in enumerate(entries, start=1):
        try:
            norm = normalize_url(entry.link)
            body = f"{entry.title}|{'' if metadata_only else (entry.summary or '')}"
            content_hash = _text_hash(body)
            existing = _find_existing(db, source, entry, norm)
            if existing is None:
                # 다른 정보원이 이미 같은 공식 문서(같은 정규화 URL)를 가지고 있으면 중복 저장하지 않는다
                other = db.scalar(select(SourceDocument).where(SourceDocument.normalized_url == norm, SourceDocument.is_latest.is_(True)).limit(1))
                if other is not None:
                    res.duplicate += 1
                    continue

            if existing is not None and existing.content_hash == content_hash:
                if existing.external_id is None and entry.external_id:  # 이전 수집분에 고유 ID/정규화 URL 보강
                    existing.external_id = entry.external_id
                if existing.normalized_url is None:
                    existing.normalized_url = norm
                res.duplicate += 1
                continue

            elsewhere = db.scalar(select(SourceDocument).where(SourceDocument.content_hash == content_hash)) if existing is None else None
            doc = SourceDocument(
                source_id=source.id,
                collection_run_id=run.id,
                title=entry.title,
                origin_url=entry.link,
                normalized_url=norm,
                external_id=entry.external_id,
                attachment_url=entry.attachment_url,
                published_at=entry.published_at,
                document_updated_at=entry.updated_at,
                collected_at=datetime.now(timezone.utc),
                raw_text=None if metadata_only else entry.summary,
                content_hash=content_hash,
                language=entry.language or detect_language(f"{entry.title} {entry.summary or ''}"),
                country_code=source.country_code,
                field_code=source.field_code,  # 실제 분야는 수집 후 자동 분류가 문서별로 다시 정한다
                collection_method=source.source_type,
                document_type=entry.document_type,
                is_peer_reviewed=entry.is_peer_reviewed,
                requires_primary_source_check=(entry.document_type == DocumentType.NEWS and not source.is_primary_source),
            )
            if existing is not None:
                # 같은 문서의 내용이 달라졌다 — 기존 행은 보존하고 새 버전으로 기록한다
                doc.status = SourceDocumentStatus.UPDATED
                doc.previous_version_id = existing.id
                doc.version_no = (existing.version_no or 1) + 1
                existing.is_latest = False
                res.updated += 1
                db.add(doc)
                db.flush()
                res.versioned.append((existing, doc))
            elif elsewhere is not None:
                doc.status = SourceDocumentStatus.DUPLICATE
                doc.duplicate_of_id = elsewhere.id
                res.duplicate += 1
                db.add(doc)
            else:
                doc.status = SourceDocumentStatus.COLLECTED
                res.new += 1
                db.add(doc)
                db.flush()
                res.new_ids.append(doc.id)
        except Exception:  # noqa: BLE001 - 한 건 실패가 전체 수집을 막지 않게 한다
            db.rollback()
            res.failed += 1
        if on_progress and (idx % 10 == 0 or idx == len(entries)):
            on_progress(idx, res)
    return res


# --------------------------------------------------------- 공통 실행 로직 ----

def run_collection(db: Session, source: Source, *, on_progress: Callable[[int, IngestResult], None] | None = None) -> CollectionRun:
    now = datetime.now(timezone.utc)
    run = CollectionRun(source_id=source.id, started_at=now, status=CollectionRunStatus.FAILED)  # 성공 시 덮어씀
    db.add(run)
    db.flush()
    source.last_attempted_at = now
    host = urlparse(source.url).hostname or ""
    url_guard.set_host_interval(host, source.min_request_interval_seconds)

    try:
        entries = _fetch_entries(source)
    except Exception as exc:  # noqa: BLE001 - 실패 유형을 분류해 그대로 기록하기 위해 넓게 잡는다
        run.status = CollectionRunStatus.FAILED
        run.error_type = classify_http_error(exc)
        run.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = datetime.now(timezone.utc)
        run.retry_count += 1
        source.consecutive_failures += 1
        source.access_status, source.access_note = access_status_for(run.error_type, exc)
        source.last_new_count = 0
        if source.consecutive_failures >= CONSECUTIVE_FAILURES_BEFORE_REVIEW:
            source.needs_review = True
        db.commit()
        db.refresh(run)
        return run

    res = ingest_entries(db, source, entries, run, on_progress=on_progress)
    run.items_found = res.found
    run.items_new = res.new
    run.items_duplicate = res.duplicate
    run.items_updated = res.updated
    run.status = CollectionRunStatus.PARTIAL if res.failed else CollectionRunStatus.SUCCESS
    run.finished_at = datetime.now(timezone.utc)
    if res.failed:
        run.error_message = f"{res.failed}건 저장 실패"
    source.consecutive_failures = 0
    source.needs_review = False
    source.last_successful_collection_at = now
    source.last_new_count = res.new
    source.access_status = "metadata_only" if source.source_type == SourceType.METADATA else "ok"
    source.access_note = "메타데이터(제목·링크·발표일)만 수집합니다" if source.source_type == SourceType.METADATA else "정상 수집"
    db.commit()
    db.refresh(run)
    run._ingest = res  # type: ignore[attr-defined]  # 작업 실행기가 후처리(분류·이슈 연결·재검토)에 사용
    return run


def backfill_document_keys(db: Session, limit: int = 2000) -> int:
    """이전 단계에서 수집한 문서에 정규화 URL·언어를 채운다(중복 판별용). 여러 번 실행해도 안전하다."""
    rows = db.scalars(select(SourceDocument).where(SourceDocument.normalized_url.is_(None)).limit(limit)).all()
    for d in rows:
        d.normalized_url = normalize_url(d.origin_url)
        if not d.language:
            d.language = detect_language(f"{d.title} {d.raw_text or ''}")
    if rows:
        db.commit()
    return len(rows)
