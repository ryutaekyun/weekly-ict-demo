"""Phase 2-3: 분류된(관련성=matched) 문서 전체를 이슈 클러스터로 묶고, 클러스터별 분석·
후보주제 추천까지 실행한다.

실행: python -m app.reprocess_issues
"""

import time

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.document_classification import DocumentClassification
from app.models.enums import ClassificationRelevance
from app.models.issue_cluster import IssueCluster
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services.issue_pipeline import run_analysis_and_recommendation_for_cluster, run_clustering_for_document


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "dev-admin@example.com").first()
        if admin is None:
            raise SystemExit("dev-admin@example.com 계정이 없습니다. 먼저 `python -m app.seed`를 실행하세요.")

        classified = (
            db.query(DocumentClassification)
            .filter(DocumentClassification.relevance == ClassificationRelevance.MATCHED)
            .all()
        )
        doc_ids = [c.document_id for c in classified]
        documents = [db.get(SourceDocument, did) for did in doc_ids]
        documents = [d for d in documents if d is not None]
        documents.sort(key=lambda d: d.published_at or d.collected_at)

        print(f"클러스터링 대상 문서 {len(documents)}건")
        started = time.time()
        ok, failed = 0, 0
        for i, doc in enumerate(documents, start=1):
            try:
                cluster = run_clustering_for_document(db, doc, actor_user_id=admin.id)
                ok += 1
                print(f"[{i}/{len(documents)}] OK {doc.title[:60]!r} -> cluster={cluster.id}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                db.rollback()
                print(f"[{i}/{len(documents)}] FAIL(clustering) {doc.title[:60]!r} -> {type(exc).__name__}: {exc}")

        print(f"\n클러스터링 완료: 성공 {ok}건 / 실패 {failed}건 ({time.time() - started:.1f}초)")

        clusters = db.scalars(select(IssueCluster)).all()
        print(f"\n생성된 클러스터 {len(clusters)}건 — 분석·추천 실행")
        a_ok, a_failed, recommended = 0, 0, 0
        for i, cluster in enumerate(clusters, start=1):
            try:
                result = run_analysis_and_recommendation_for_cluster(
                    db, cluster, created_by_user_id=admin.id, prefer_ai=True
                )
                a_ok += 1
                if result is not None:
                    recommended += 1
                print(f"[{i}/{len(clusters)}] OK analyze+recommend {cluster.title[:50]!r} -> recommended={result is not None}")
            except Exception as exc:  # noqa: BLE001
                a_failed += 1
                db.rollback()
                print(f"[{i}/{len(clusters)}] FAIL(analysis) {cluster.title[:50]!r} -> {type(exc).__name__}: {exc}")

        print(f"\n분석 완료: 성공 {a_ok}건 / 실패 {a_failed}건, 후보주제 추천 {recommended}건")
    finally:
        db.close()


if __name__ == "__main__":
    main()
