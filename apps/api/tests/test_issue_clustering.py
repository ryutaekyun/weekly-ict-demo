from datetime import datetime, timezone

from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.enums import (
    ClassificationMethod,
    ClassificationRelevance,
    DocumentType,
    ExtractionMethod,
    ExtractionStatus,
    FieldCode,
    IssueMembershipType,
    SourceDocumentStatus,
    SourceType,
)
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.issue_pipeline import run_clustering_for_document


def _make_source(db_session, field_code=FieldCode.SW) -> Source:
    source = Source(
        name="Test Source", org_name="Test Agency", field_code=field_code, country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_doc(db_session, source, *, title, published_at, field_code, full_text=""):
    doc = SourceDocument(
        source_id=source.id, title=title, origin_url=f"https://example.org/{title[:20]}",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash=title,
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code, collection_method=SourceType.RSS,
        document_type=DocumentType.POLICY, published_at=published_at,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    db_session.add(DocumentClassification(
        document_id=doc.id, primary_field_code=field_code, relevance=ClassificationRelevance.MATCHED,
        method=ClassificationMethod.RULE_BASED, classified_at=datetime.now(timezone.utc),
    ))
    db_session.add(DocumentFullText(
        document_id=doc.id, full_text=full_text, extraction_status=ExtractionStatus.SUCCESS,
        extraction_method=ExtractionMethod.HTML, char_count=len(full_text), extracted_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    return doc


def test_same_rin_clusters_together_even_across_different_field_classification(db_session):
    """실데이터 재현 — 동일 RIN이 서로 다른 분야로 분류돼도 하나의 클러스터로 묶여야 한다."""
    source = _make_source(db_session)
    doc1 = _make_doc(
        db_session, source, title="Proposed Rule on Widget Safety", published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        field_code=FieldCode.BCAST, full_text="This notice concerns RIN 1234-AB56 widget safety standards.",
    )
    doc2 = _make_doc(
        db_session, source, title="Final Rule on Widget Safety", published_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        field_code=FieldCode.SW, full_text="This final rule under RIN 1234-AB56 confirms widget safety standards.",
    )

    cluster1 = run_clustering_for_document(db_session, doc1)
    cluster2 = run_clustering_for_document(db_session, doc2)

    assert cluster1.id == cluster2.id


def test_different_rin_does_not_cluster_despite_similar_title(db_session):
    source = _make_source(db_session)
    doc1 = _make_doc(
        db_session, source, title="Export Control Updates for Semiconductor Items",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="RIN 1111-AA11 covers export control updates.",
    )
    doc2 = _make_doc(
        db_session, source, title="Export Control Updates for Semiconductor Items Part 2",
        published_at=datetime(2024, 1, 5, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="RIN 2222-BB22 covers a separate export control updates action.",
    )

    cluster1 = run_clustering_for_document(db_session, doc1)
    cluster2 = run_clustering_for_document(db_session, doc2)

    # 서로 다른 RIN은 강한 신호가 우선 적용되어 묶이지 않아야 한다(제목 유사도만으로 합치지 않음)
    assert cluster1.id != cluster2.id


def test_weak_title_similarity_match_flags_needs_review(db_session):
    source = _make_source(db_session)
    doc1 = _make_doc(
        db_session, source, title="Quantum Computing Research Funding Announcement",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="No identifying docket number here.",
    )
    doc2 = _make_doc(
        db_session, source, title="Quantum Computing Research Funding Updates",
        published_at=datetime(2024, 1, 10, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="No identifying docket number here either.",
    )

    cluster1 = run_clustering_for_document(db_session, doc1)
    cluster2 = run_clustering_for_document(db_session, doc2)

    assert cluster1.id == cluster2.id
    from app.models.enums import ClusterReviewStatus
    assert cluster2.review_status == ClusterReviewStatus.NEEDS_REVIEW


def test_hub_document_spanning_two_rins_flags_cluster_for_review(db_session):
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — 설명회 1건이 서로 다른 두 규제조치의
    RIN을 함께 언급하면, 두 조치가 한 클러스터로 묶여도 자동 확정하지 말고 검토 대기로 둬야 한다."""
    source = _make_source(db_session)
    briefing = _make_doc(
        db_session, source, title="Public Briefing on Two Separate Actions",
        published_at=datetime(2024, 12, 4, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="This briefing covers RIN 0694-AJ74 and RIN 0694-AJ77.",
    )
    action_a = _make_doc(
        db_session, source, title="Foreign-Produced Direct Product Rule Additions",
        published_at=datetime(2024, 12, 5, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="RIN 0694-AJ74 covers this specific rule.",
    )
    action_b = _make_doc(
        db_session, source, title="Entity List Additions and Modifications",
        published_at=datetime(2024, 12, 5, tzinfo=timezone.utc), field_code=FieldCode.SEMI,
        full_text="RIN 0694-AJ77 covers this separate, unrelated rule.",
    )

    run_clustering_for_document(db_session, briefing)
    run_clustering_for_document(db_session, action_a)
    final_cluster = run_clustering_for_document(db_session, action_b)

    from app.models.enums import ClusterReviewStatus
    assert final_cluster.review_status == ClusterReviewStatus.NEEDS_REVIEW


def test_same_rin_different_docket_across_rulemaking_phases_is_not_flagged_as_hub(db_session):
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — 동일 RIN이라도 NPRM 단계와 Final Rule
    단계에서 기관이 새 Docket 번호를 부여하는 것은 정상이다. RIN으로 이미 매칭됐다면 Docket이
    달라도 허브 문서로 잘못 의심해 검토 대기로 돌리면 안 된다."""
    source = _make_source(db_session)
    proposed = _make_doc(
        db_session, source, title="Proposed Rule on Electric Powertrain",
        published_at=datetime(2024, 4, 15, tzinfo=timezone.utc), field_code=FieldCode.SW,
        full_text="RIN 2127-AM43, Docket No. NHTSA-2024-0012.",
    )
    final = _make_doc(
        db_session, source, title="Final Rule on Electric Powertrain",
        published_at=datetime(2024, 12, 20, tzinfo=timezone.utc), field_code=FieldCode.BCAST,
        full_text="RIN 2127-AM43, Docket No. NHTSA-2024-0091.",
    )

    run_clustering_for_document(db_session, proposed)
    final_cluster = run_clustering_for_document(db_session, final)

    from app.models.enums import ClusterReviewStatus
    assert final_cluster.review_status == ClusterReviewStatus.CONFIRMED


def test_unrelated_documents_do_not_cluster(db_session):
    source = _make_source(db_session)
    doc1 = _make_doc(
        db_session, source, title="Semiconductor Export Control Policy Update",
        published_at=datetime(2024, 1, 1, tzinfo=timezone.utc), field_code=FieldCode.SEMI, full_text="x",
    )
    doc2 = _make_doc(
        db_session, source, title="Streaming Service Copyright Fraud Investigation",
        published_at=datetime(2024, 1, 2, tzinfo=timezone.utc), field_code=FieldCode.CONTENT, full_text="y",
    )

    cluster1 = run_clustering_for_document(db_session, doc1)
    cluster2 = run_clustering_for_document(db_session, doc2)

    assert cluster1.id != cluster2.id
