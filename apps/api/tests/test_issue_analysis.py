import json
from datetime import datetime, timezone

from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
from app.models.enums import (
    ClassificationMethod,
    ClassificationRelevance,
    ClusterReviewStatus,
    DisputeAnalysisStatus,
    DocumentType,
    ExtractionMethod,
    ExtractionStatus,
    FieldCode,
    IssueMembershipType,
    SourceDocumentStatus,
    SourceType,
)
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import issue_analysis as issue_analysis_service


def _make_source(db_session, country="US") -> Source:
    source = Source(
        name="Test", org_name="Test Agency", field_code=FieldCode.AI, country_code=country,
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_cluster_with_doc(db_session, source, *, title, full_text, published_at=None):
    doc = SourceDocument(
        source_id=source.id, title=title, origin_url=f"https://example.org/{title[:15]}",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash=title,
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code, collection_method=SourceType.RSS,
        document_type=DocumentType.POLICY, published_at=published_at or datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    db_session.add(DocumentFullText(
        document_id=doc.id, full_text=full_text, extraction_status=ExtractionStatus.SUCCESS,
        extraction_method=ExtractionMethod.HTML, char_count=len(full_text), extracted_at=datetime.now(timezone.utc),
    ))
    cluster = IssueCluster(
        title=title, field_code=source.field_code, first_seen_at=doc.published_at,
        representative_document_id=doc.id, last_activity_at=doc.published_at,
        review_status=ClusterReviewStatus.CONFIRMED, created_by_method=ClassificationMethod.RULE_BASED,
    )
    db_session.add(cluster)
    db_session.flush()
    db_session.add(IssueClusterDocument(
        issue_cluster_id=cluster.id, document_id=doc.id, membership_type=IssueMembershipType.PRIMARY,
        similarity_score=None, method=ClassificationMethod.RULE_BASED,
    ))
    db_session.commit()
    return cluster, doc


def test_no_dispute_signal_is_confirmed_no_disputes(db_session, monkeypatch):
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(
        db_session, source, title="Routine Policy Update", full_text="This is a routine policy update with no controversy."
    )

    result = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)

    assert result.dispute_status == DisputeAnalysisStatus.NO_DISPUTES_CONFIRMED


def test_dispute_signal_phrase_is_detected_and_flagged_for_review(db_session, monkeypatch):
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(
        db_session, source, title="Contested Rule",
        full_text="Industry groups argue that the rule imposes undue burden, while the agency disagreed with this assessment.",
    )

    result = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)

    assert result.dispute_status == DisputeAnalysisStatus.DISPUTES_FOUND

    from app.models.issue_dispute_point import IssueDisputePoint
    disputes = db_session.query(IssueDisputePoint).filter_by(issue_cluster_id=cluster.id).all()
    assert len(disputes) >= 1
    assert "확인 필요" in disputes[0].dispute_title


def test_as_opposed_to_idiom_is_not_a_false_dispute_signal(db_session, monkeypatch):
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — 'A as opposed to B'는 비교 관용구일 뿐
    이해관계자 간 분쟁이 아니다."""
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(
        db_session, source, title="Technical Comparison",
        full_text="NHTSA considered a 6-year-old child as opposed to the 5th percentile female dummy for testing.",
    )

    result = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)

    assert result.dispute_status == DisputeAnalysisStatus.NO_DISPUTES_CONFIRMED


def test_reanalysis_clears_stale_dispute_rows_when_no_longer_found(db_session, monkeypatch):
    """실데이터 검증에서 발견한 실제 결함 재발 방지 — 재분석 결과 논쟁이 더 이상 감지되지
    않으면, 이전 실행에서 만든 IssueDisputePoint 행도 함께 지워져야 한다."""
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(
        db_session, source, title="Disputed Then Clarified",
        full_text="Industry groups argue the rule is too strict and the agency disagreed with this view.",
    )

    first = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)
    assert first.dispute_status == DisputeAnalysisStatus.DISPUTES_FOUND

    from app.models.document_full_text import DocumentFullText

    ft = db_session.query(DocumentFullText).filter_by(document_id=doc.id).one()
    ft.full_text = "A perfectly uncontroversial routine update with no dispute signals at all."
    db_session.commit()

    second = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)
    assert second.dispute_status == DisputeAnalysisStatus.NO_DISPUTES_CONFIRMED

    from app.models.issue_dispute_point import IssueDisputePoint
    remaining = db_session.query(IssueDisputePoint).filter_by(issue_cluster_id=cluster.id).count()
    assert remaining == 0


def test_single_country_data_does_not_fabricate_foreign_positions(db_session, monkeypatch):
    """지시사항: 국가별 자료가 없으면 임의로 해당 국가의 입장을 작성하지 않는다."""
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session, country="US")
    cluster, doc = _make_cluster_with_doc(db_session, source, title="US-only Policy", full_text="A US policy document.")

    result = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)

    positions = json.loads(result.country_positions_json)
    non_us_entries = [p for p in positions if p["country_or_org"] not in (None, "US")]
    assert non_us_entries == []
    assert any("임의로" in p["position_summary"] for p in positions if p["country_or_org"] is None)


def test_domestic_relevance_not_fabricated_in_rule_based_mode(db_session, monkeypatch):
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(db_session, source, title="Some Policy", full_text="Some policy text.")

    result = issue_analysis_service.run_issue_analysis(db_session, cluster, prefer_ai=True)

    assert result.domestic_has_sufficient_basis is False
    assert result.domestic_industry_relevance is None
    assert result.generated_by == ClassificationMethod.RULE_BASED
