"""GitHub Actions CI 전용 — Playwright 브라우저 E2E 테스트가 다룰 최소한의 실데이터 모양
샘플을 만든다. 실제 외부 수집(네트워크 호출) 없이 합성 데이터로 실제 클러스터링·분석·
추천 파이프라인(run_clustering_for_document, run_analysis_and_recommendation_for_cluster)을
그대로 실행해, 로직 자체는 실제 코드 경로를 타면서도 CI에서는 결정적으로 동작하게 한다.

로컬 개발용 dev.db에는 실제 수집 데이터(255건)가 이미 있으므로 이 스크립트를 실행할
필요가 없다 — CI의 빈 PostgreSQL에서만 사용한다.

실행: python -m app.seed_ci_fixtures
"""

from datetime import datetime, timezone

from app.core.db import Base, SessionLocal, engine
from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.document_structured_extract import DocumentStructuredExtract
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.enums import (
    ClassificationMethod,
    ClassificationRelevance,
    DocumentType,
    ExtractionMethod,
    ExtractionStatus,
    FieldCode,
    SourceDocumentStatus,
    SourceType,
    UsageValueRating,
    VerificationStatus,
)
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.seed import seed as seed_dummy_users
from app.seed_e2e_test_user import seed_e2e_test_users
from app.services.issue_pipeline import run_analysis_and_recommendation_for_cluster, run_clustering_for_document


def _make_doc(db, source: Source, *, title: str, full_text: str, field_code: FieldCode, published_at) -> SourceDocument:
    doc = SourceDocument(
        source_id=source.id, title=title, origin_url=f"https://example.org/ci/{abs(hash(title))}",
        collected_at=datetime.now(timezone.utc), raw_text=full_text, content_hash=title,
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code, collection_method=SourceType.RSS,
        document_type=DocumentType.POLICY, published_at=published_at,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    db.add(DocumentClassification(
        document_id=doc.id, primary_field_code=field_code, relevance=ClassificationRelevance.MATCHED,
        method=ClassificationMethod.RULE_BASED, classified_at=datetime.now(timezone.utc),
        reasoning="CI 픽스처 — 합성 데이터",
    ))
    db.add(DocumentFullText(
        document_id=doc.id, full_text=full_text, extraction_status=ExtractionStatus.SUCCESS,
        extraction_method=ExtractionMethod.HTML, char_count=len(full_text), extracted_at=datetime.now(timezone.utc),
    ))
    db.add(DocumentValueAssessment(
        document_id=doc.id, rating=UsageValueRating.GENERAL, method=ClassificationMethod.RULE_BASED,
        evidence_quote=full_text[:80],
    ))
    db.add(DocumentStructuredExtract(
        document_id=doc.id, key_content=full_text[:120], background_purpose="CI 테스트용 배경 설명",
        verification_status=VerificationStatus.UNVERIFIED, generated_by=ClassificationMethod.RULE_BASED,
    ))
    db.commit()
    return doc


def seed_ci_fixtures() -> None:
    Base.metadata.create_all(bind=engine)
    seed_dummy_users()
    seed_e2e_test_users()

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == "dev-admin@example.com").one()

        source = Source(
            name="CI Fixture Source", org_name="CI Fixture Agency", field_code=FieldCode.AI, country_code="US",
            url="https://example.org/ci-fixture-feed", source_type=SourceType.RSS, is_primary_source=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)

        # 동일 RIN을 공유하는 두 문서 — 실제 클러스터링 로직으로 하나의 복수문서 이슈가 되어야 한다.
        doc1 = _make_doc(
            db, source, title="CI Fixture: Proposed AI Safety Rule",
            full_text=("This notice concerns RIN 9999-CI01 artificial intelligence safety standards for CI testing.\n\n"
                       "The agency proposes that providers of high-risk systems document their evaluation methods by March 1, 2027.\n\n"
                       "Comments on the proposed requirements are due within 60 days of publication in the fixture register."),
            field_code=FieldCode.AI, published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        doc2 = _make_doc(
            db, source, title="CI Fixture: Final AI Safety Rule",
            full_text=("This final rule under RIN 9999-CI01 confirms artificial intelligence safety standards for CI testing.\n\n"
                       "The final requirements take effect on July 1, 2027 and apply to providers with more than 100 employees.\n\n"
                       "Industry commenters asked for a longer transition period, while consumer groups supported the original schedule."),
            field_code=FieldCode.AI, published_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        # 독립된 단일 문서 이슈 — 목록·필터 화면에 다양한 사례가 보이도록 한다.
        doc3 = _make_doc(
            db, source, title="CI Fixture: Standalone Semiconductor Notice",
            full_text="This is an independent notice about semiconductor export control for CI testing purposes.",
            field_code=FieldCode.SEMI, published_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        )

        for doc in (doc1, doc2, doc3):
            cluster = run_clustering_for_document(db, doc, actor_user_id=admin.id)
            run_analysis_and_recommendation_for_cluster(db, cluster, created_by_user_id=admin.id, prefer_ai=True)

        print("CI 픽스처 데이터 생성 완료: 문서 3건(복수문서 이슈 1건 + 단일문서 이슈 1건), 후보주제·점수 포함")
    finally:
        db.close()


if __name__ == "__main__":
    seed_ci_fixtures()
