"""연방관보 공개 문서를 번호로 DB에 추가한다(검증 계획용 1~3건 단위 수동 추가 — 대규모 수집이 아님).

기존 수집·전문추출·분류·이슈 통합 파이프라인을 그대로 쓰며 AI는 호출하지 않는다(prefer_ai=False).
실행: python -m app.add_public_documents 2025-02582 2026-11072
"""

import sys
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.enums import DocumentType, SourceDocumentStatus
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.collection import _content_hash
from app.services.issue_pipeline import run_clustering_for_document
from app.services.pipeline import run_full_pipeline

FR_API = "https://www.federalregister.gov/api/v1/documents"
TYPE_MAP = {"RULE": DocumentType.LAW, "PROPOSED RULE": DocumentType.LAW}


def add(db, number: str) -> SourceDocument:
    d = httpx.get(f"{FR_API}/{number}.json", timeout=30).json()
    link = d["html_url"]
    existing = db.scalar(select(SourceDocument).where(SourceDocument.origin_url == link))
    if existing is not None:
        print(f"이미 있음: {number}")
        return existing
    ref = db.scalar(select(SourceDocument).where(SourceDocument.origin_url.like("%federalregister.gov%")).order_by(SourceDocument.collected_at))
    source = db.get(Source, ref.source_id)
    published = datetime.strptime(d["publication_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    doc = SourceDocument(
        source_id=source.id, collection_run_id=ref.collection_run_id, title=d["title"].strip(), origin_url=link, attachment_url=d.get("pdf_url"),
        published_at=published, collected_at=datetime.now(timezone.utc), raw_text=d.get("abstract"), content_hash=_content_hash(d["title"], link),
        country_code=source.country_code, field_code=source.field_code, collection_method=source.source_type,
        document_type=TYPE_MAP.get((d.get("type") or "").upper(), DocumentType.POLICY), status=SourceDocumentStatus.COLLECTED,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    run_full_pipeline(db, doc, source, prefer_ai=False)
    cluster = run_clustering_for_document(db, doc)
    db.commit()
    print(f"추가: {number} → 이슈 {cluster.id} ({cluster.title[:60]})")
    return doc


def main() -> None:
    db = SessionLocal()
    try:
        for n in sys.argv[1:]:
            add(db, n)
    finally:
        db.close()


if __name__ == "__main__":
    main()
