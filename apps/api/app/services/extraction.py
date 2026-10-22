"""원문 전문(full text) 추출 — HTML 본문 추출 + PDF 텍스트 추출.

원칙:
- 기존 수집기(collection.py)와 같은 User-Agent/타임아웃을 쓰고, robots.txt를 확인해 허용되지
  않은 경로는 시도 자체를 하지 않는다(ExtractionStatus.NOT_ATTEMPTED).
- PDF에서 페이지당 평균 추출 글자 수가 매우 낮으면(스캔본으로 추정) SUCCESS로 표시하지 않는다.
- 전문을 구하지 못했다고 전체 파이프라인을 실패시키지 않는다 — SUMMARY_ONLY/FAILED로 기록하고
  분류·가치판정은 기존 요약문(raw_text)으로 계속 진행한다.
"""

import hashlib
import io
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.models.document_full_text import DocumentFullText
from app.models.enums import ExtractionMethod, ExtractionStatus
from app.models.source_document import SourceDocument

USER_AGENT = "TNP-AI-Platform-Collector/0.1 (ICT research collection; contact: platform-admin@tenopa.co.kr)"
FETCH_TIMEOUT_SECONDS = 20.0
MAX_PDF_BYTES = 25 * 1024 * 1024
MIN_CHARS_PER_PDF_PAGE_FOR_SUCCESS = 20
BLOCK_TAGS = ["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]


@dataclass
class ExtractionResult:
    full_text: str | None
    status: ExtractionStatus
    method: ExtractionMethod
    char_count: int
    source_location: str | None
    failure_reason: str | None


def _robots_allowed(url: str) -> bool:
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = urllib.robotparser.RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:  # noqa: BLE001 - robots.txt 접근 실패는 "허용"으로 간주(보수적으로 막지 않음)
        return True
    try:
        return rp.can_fetch(USER_AGENT, url)
    except Exception:  # noqa: BLE001
        return True


def _largest_text_block(soup: BeautifulSoup):
    for tag in soup(BLOCK_TAGS):
        tag.decompose()
    article = soup.find("article") or soup.find("main")
    if article is not None and len(article.get_text(strip=True)) > 200:
        return article, "본문 <article>/<main> 태그 기준"
    candidates = soup.find_all(["div", "section"])
    best = None
    best_len = 0
    for cand in candidates:
        paragraphs = cand.find_all("p", recursive=False)
        text_len = sum(len(p.get_text(strip=True)) for p in paragraphs)
        if text_len > best_len:
            best_len = text_len
            best = cand
    if best is not None and best_len > 200:
        return best, "최다 텍스트 블록(<div>/<section>) 기준"
    return soup.body or soup, "페이지 전체 <body> 기준(본문 영역을 특정하지 못함)"


def _detect_language(text: str) -> str:
    if not text:
        return "und"
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    if hangul / max(len(text), 1) > 0.05:
        return "ko"
    return "en"


def extract_html_full_text(url: str) -> ExtractionResult:
    if not _robots_allowed(url):
        return ExtractionResult(
            full_text=None,
            status=ExtractionStatus.NOT_ATTEMPTED,
            method=ExtractionMethod.NONE,
            char_count=0,
            source_location=None,
            failure_reason="robots.txt에서 이 경로의 수집을 허용하지 않음",
        )
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type and "<html" not in resp.text[:500].lower():
                return ExtractionResult(
                    full_text=None,
                    status=ExtractionStatus.FAILED,
                    method=ExtractionMethod.NONE,
                    char_count=0,
                    source_location=None,
                    failure_reason=f"HTML이 아닌 콘텐츠 타입: {content_type or 'unknown'}",
                )
            html = resp.text
    except httpx.HTTPError as exc:
        return ExtractionResult(
            full_text=None,
            status=ExtractionStatus.FAILED,
            method=ExtractionMethod.NONE,
            char_count=0,
            source_location=None,
            failure_reason=f"HTTP 요청 실패: {type(exc).__name__}: {exc}",
        )

    soup = BeautifulSoup(html, "html.parser")
    block, location = _largest_text_block(soup)
    paragraphs = [p.get_text(" ", strip=True) for p in block.find_all("p")]
    paragraphs = [p for p in paragraphs if p]
    text = "\n\n".join(paragraphs) if paragraphs else block.get_text("\n", strip=True)
    text = text.strip()

    if len(text) < 100:
        return ExtractionResult(
            full_text=text or None,
            status=ExtractionStatus.FAILED,
            method=ExtractionMethod.HTML,
            char_count=len(text),
            source_location=location,
            failure_reason="추출된 본문이 너무 짧음(100자 미만) — 페이지 구조를 특정하지 못했을 가능성",
        )

    return ExtractionResult(
        full_text=text,
        status=ExtractionStatus.SUCCESS,
        method=ExtractionMethod.HTML,
        char_count=len(text),
        source_location=f"{location}, {len(paragraphs)}개 문단",
        failure_reason=None,
    )


def extract_pdf_full_text(url: str) -> ExtractionResult:
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_length = int(resp.headers.get("content-length") or len(resp.content))
            if content_length > MAX_PDF_BYTES:
                return ExtractionResult(
                    full_text=None,
                    status=ExtractionStatus.NOT_ATTEMPTED,
                    method=ExtractionMethod.NONE,
                    char_count=0,
                    source_location=None,
                    failure_reason=f"PDF 용량 제한 초과({content_length} bytes > {MAX_PDF_BYTES})",
                )
            pdf_bytes = resp.content
    except httpx.HTTPError as exc:
        return ExtractionResult(
            full_text=None,
            status=ExtractionStatus.FAILED,
            method=ExtractionMethod.NONE,
            char_count=0,
            source_location=None,
            failure_reason=f"PDF 다운로드 실패: {type(exc).__name__}: {exc}",
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 - 손상/암호화 PDF 등 다양한 실패를 모두 FAILED로 기록
        return ExtractionResult(
            full_text=None,
            status=ExtractionStatus.FAILED,
            method=ExtractionMethod.NONE,
            char_count=0,
            source_location=None,
            failure_reason=f"PDF 파싱 실패: {type(exc).__name__}: {exc}",
        )

    num_pages = len(page_texts)
    text = "\n\n".join(t.strip() for t in page_texts if t.strip())
    char_count = len(text)
    location = f"PDF p.1-{num_pages}(총 {num_pages}p)"

    if num_pages == 0:
        return ExtractionResult(
            full_text=None, status=ExtractionStatus.FAILED, method=ExtractionMethod.PDF,
            char_count=0, source_location=None, failure_reason="페이지를 읽지 못함(빈 PDF 또는 파싱 실패)",
        )

    avg_chars_per_page = char_count / num_pages
    if avg_chars_per_page < MIN_CHARS_PER_PDF_PAGE_FOR_SUCCESS:
        return ExtractionResult(
            full_text=text or None,
            status=ExtractionStatus.FAILED,
            method=ExtractionMethod.PDF,
            char_count=char_count,
            source_location=location,
            failure_reason=(
                f"페이지당 평균 추출 글자 수가 {avg_chars_per_page:.1f}자로 매우 낮음 — "
                "스캔본(이미지 PDF)이라 텍스트 레이어가 없는 것으로 추정"
            ),
        )

    return ExtractionResult(
        full_text=text, status=ExtractionStatus.SUCCESS, method=ExtractionMethod.PDF,
        char_count=char_count, source_location=location, failure_reason=None,
    )


def derive_arxiv_pdf_url(origin_url: str) -> str | None:
    """arXiv 초록 페이지(/abs/<id>) URL에서 전문 PDF URL을 유도한다. arXiv가 아니면 None."""
    if "arxiv.org/abs/" not in origin_url:
        return None
    return origin_url.replace("/abs/", "/pdf/")


def content_hash_of(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def extract_full_text_for_document(*, origin_url: str, attachment_url: str | None) -> ExtractionResult:
    """우선순위: 첨부 PDF(attachment_url) > arXiv 전문 PDF 유도 > origin_url의 HTML 본문."""
    if attachment_url and attachment_url.lower().endswith(".pdf"):
        result = extract_pdf_full_text(attachment_url)
        if result.status == ExtractionStatus.SUCCESS:
            return result
        # PDF가 실패하면 origin_url의 HTML이라도 시도해 본다(완전히 포기하지 않음)
        html_fallback = extract_html_full_text(origin_url)
        if html_fallback.status == ExtractionStatus.SUCCESS:
            return html_fallback
        return result

    arxiv_pdf = derive_arxiv_pdf_url(origin_url)
    if arxiv_pdf:
        pdf_result = extract_pdf_full_text(arxiv_pdf)
        if pdf_result.status == ExtractionStatus.SUCCESS:
            return pdf_result

    return extract_html_full_text(origin_url)


def run_extraction(db: Session, document: SourceDocument) -> DocumentFullText:
    """문서 1건의 전문을 추출해 DocumentFullText를 생성/갱신(이력 체인)하고 반환한다."""
    result = extract_full_text_for_document(origin_url=document.origin_url, attachment_url=document.attachment_url)
    now = datetime.now(timezone.utc)

    existing = db.query(DocumentFullText).filter_by(document_id=document.id).one_or_none()
    new_hash = content_hash_of(result.full_text) if result.full_text else None
    content_changed = bool(existing and existing.content_hash and new_hash and existing.content_hash != new_hash)
    previous_id = existing.id if (existing and content_changed) else None

    if existing is None or content_changed:
        record = DocumentFullText(
            document_id=document.id,
            full_text=result.full_text,
            extraction_status=result.status,
            extraction_method=result.method,
            char_count=result.char_count,
            content_hash=new_hash,
            source_location=result.source_location,
            content_changed=content_changed,
            previous_extraction_id=previous_id,
            failure_reason=result.failure_reason,
            extracted_at=now,
        )
        db.add(record)
    else:
        record = existing
        record.full_text = result.full_text
        record.extraction_status = result.status
        record.extraction_method = result.method
        record.char_count = result.char_count
        record.content_hash = new_hash
        record.source_location = result.source_location
        record.content_changed = False
        record.failure_reason = result.failure_reason
        record.extracted_at = now

    if result.full_text and not document.language:
        document.language = _detect_language(result.full_text)

    db.flush()
    return record
