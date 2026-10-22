"""기존 수집 문서 전체에 Phase 2-2 파이프라인(전문추출 -> 분류 -> 가치판정 -> 구조화)을 적용한다.

기존 문서를 삭제하지 않는다 — SourceDocument는 그대로 두고, 그 위에 분류/전문/가치판정/구조화
레코드를 새로 생성(또는 재실행 시 갱신)한다.

실행: python -m app.reprocess_documents [--limit N] [--field ai] [--status collected,updated]
"""

import argparse
import time

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.enums import FieldCode, SourceDocumentStatus
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.pipeline import run_full_pipeline


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--field", type=str, default=None, help="특정 분야(출처 기준)만 처리, 예: ai")
    parser.add_argument(
        "--include-duplicates", action="store_true", help="DUPLICATE 상태 문서도 처리(기본은 제외)"
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stmt = select(SourceDocument)
        if not args.include_duplicates:
            stmt = stmt.where(SourceDocument.status != SourceDocumentStatus.DUPLICATE)
        if args.field:
            source_ids = [s.id for s in db.query(Source).filter(Source.field_code == FieldCode(args.field)).all()]
            stmt = stmt.where(SourceDocument.source_id.in_(source_ids))
        if args.limit:
            stmt = stmt.limit(args.limit)

        documents = db.scalars(stmt).all()
        total = len(documents)
        print(f"재처리 대상 문서 {total}건")

        source_cache: dict = {}
        ok, failed = 0, 0
        started = time.time()
        for i, doc in enumerate(documents, start=1):
            if doc.source_id not in source_cache:
                source_cache[doc.source_id] = db.get(Source, doc.source_id)
            source = source_cache[doc.source_id]
            try:
                result = run_full_pipeline(db, doc, source, prefer_ai=True)
                ok += 1
                print(
                    f"[{i}/{total}] OK {doc.title[:50]!r} -> "
                    f"field={result.classification.primary_field_code}, "
                    f"relevance={result.classification.relevance.value}, "
                    f"extraction={result.full_text.extraction_status.value}, "
                    f"value={result.value_assessment.rating.value}"
                )
            except Exception as exc:  # noqa: BLE001 - 한 건 실패로 전체를 중단하지 않는다
                failed += 1
                db.rollback()
                print(f"[{i}/{total}] FAIL {doc.title[:50]!r} -> {type(exc).__name__}: {exc}")

        elapsed = time.time() - started
        print(f"\n완료: 성공 {ok}건 / 실패 {failed}건 (총 {total}건, {elapsed:.1f}초 소요)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
