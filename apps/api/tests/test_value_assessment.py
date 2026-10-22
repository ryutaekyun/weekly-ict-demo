from datetime import datetime, timedelta, timezone

from app.models.enums import DocumentType, FieldCode, SourceType, UsageValueRating
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import value_assessment as value_assessment_service


def _make_source(db_session, is_primary=True, tier=1) -> Source:
    source = Source(
        name="Test Source", org_name="Test Agency", field_code=FieldCode.AI, country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=is_primary,
        reliability_tier=tier,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_document(db_session, source, *, published_days_ago=5, document_type=DocumentType.POLICY) -> SourceDocument:
    from app.models.enums import SourceDocumentStatus

    doc = SourceDocument(
        source_id=source.id, title="Test", origin_url="https://example.org/a",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash="x",
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code,
        collection_method=SourceType.RSS, document_type=document_type,
        published_at=datetime.now(timezone.utc) - timedelta(days=published_days_ago),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_recency_bucket_computed_dynamically_not_all_lumped_as_recent():
    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    assert value_assessment_service.compute_recency_bucket(now - timedelta(days=3), reference_time=now) == "within_7d"
    assert value_assessment_service.compute_recency_bucket(now - timedelta(days=20), reference_time=now) == "within_30d"
    assert value_assessment_service.compute_recency_bucket(now - timedelta(days=60), reference_time=now) == "within_90d"
    assert value_assessment_service.compute_recency_bucket(now - timedelta(days=400), reference_time=now) == "older"
    assert value_assessment_service.compute_recency_bucket(None, reference_time=now) == "unknown"


def test_priority_rating_for_important_primary_recent_document(db_session):
    source = _make_source(db_session, is_primary=True, tier=1)
    doc = _make_document(db_session, source, published_days_ago=10, document_type=DocumentType.LAW)
    text = "This regulation requires compliance with new reporting standards effective immediately. " * 10

    result = value_assessment_service.assess_document_value_rule_based(
        document=doc, source=source, text=text, is_relevant_to_9_fields=True
    )

    assert result.rating == UsageValueRating.PRIORITY


def test_administrative_boilerplate_dominated_notice_is_downgraded(db_session):
    source = _make_source(db_session)
    doc = _make_document(db_session, source, document_type=DocumentType.POLICY)
    text = (
        "This notice is issued under the Paperwork Reduction Act. OMB control number 1234-5678 applies. "
        "Agency Information Collection Activities are described below for Paperwork Reduction Act purposes. "
        "Paperwork Reduction Act compliance is required for this Agency Information Collection Activities notice."
    )

    result = value_assessment_service.assess_document_value_rule_based(
        document=doc, source=source, text=text, is_relevant_to_9_fields=True
    )

    assert result.rating == UsageValueRating.LOW_RELEVANCE
    assert "행정" in result.reasoning


def test_rfi_notice_with_substantive_content_is_not_auto_excluded():
    """지시사항: RFI·의견수렴 공고는 문서유형만으로 일괄 배제하지 않는다."""
    from app.models.enums import DocumentType as DT

    # NOTICE 타입이라도 실질적 정책 신호(규제, 기준, 시행일)가 있으면 LOW_RELEVANCE로 자동 강등되지 않아야 한다
    text = (
        "This Request for Information seeks public comment on proposed requirements and technical standards "
        "for the regulation of artificial intelligence systems, with an effective date set for next year. "
        "The proposed rule establishes new compliance requirements and deadlines for industry stakeholders."
    )
    assert value_assessment_service._is_administrative_boilerplate_dominated(text) is False


def test_insufficient_content_needs_more_info(db_session):
    source = _make_source(db_session)
    doc = _make_document(db_session, source)
    text = "Too short."

    result = value_assessment_service.assess_document_value_rule_based(
        document=doc, source=source, text=text, is_relevant_to_9_fields=True
    )

    assert result.rating == UsageValueRating.NEEDS_MORE_INFO


def test_low_relevance_classification_propagates_to_value_assessment(db_session):
    source = _make_source(db_session)
    doc = _make_document(db_session, source)
    text = "Some generic unrelated text that is long enough to pass the content sufficiency bar here. " * 5

    result = value_assessment_service.assess_document_value_rule_based(
        document=doc, source=source, text=text, is_relevant_to_9_fields=False
    )

    assert result.rating == UsageValueRating.LOW_RELEVANCE
