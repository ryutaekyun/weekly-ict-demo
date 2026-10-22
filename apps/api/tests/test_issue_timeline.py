from datetime import datetime, timezone
import uuid

from app.models.enums import DocumentType, IssueMembershipType, SourceDocumentStatus, SourceType
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services.issue_timeline import record_timeline_event


def _make_doc(db_session, source, title, published_at):
    doc = SourceDocument(
        source_id=source.id, title=title, origin_url=f"https://example.org/{title[:15]}",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash=title,
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code, collection_method=SourceType.RSS,
        document_type=DocumentType.POLICY, published_at=published_at,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _make_source(db_session):
    source = Source(
        name="Test", org_name="Test Agency", field_code="sw", country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def test_first_document_is_new_issue(db_session):
    source = _make_source(db_session)
    doc = _make_doc(db_session, source, "Notice of Proposed Rulemaking on X", datetime(2024, 1, 1, tzinfo=timezone.utc))

    event = record_timeline_event(
        db_session, cluster_id=uuid.uuid4(), document=doc,
        membership_type=IssueMembershipType.PRIMARY, previous_document=None,
    )

    from app.models.enums import TimelineEventType
    assert event.event_type == TimelineEventType.NEW_ISSUE
    assert event.compared_to_document_id is None


def test_proposed_to_final_is_substantive_change(db_session):
    source = _make_source(db_session)
    proposed = _make_doc(db_session, source, "Proposed Rule on Widget Safety", datetime(2024, 1, 1, tzinfo=timezone.utc))
    final = _make_doc(db_session, source, "Final Rule on Widget Safety", datetime(2024, 6, 1, tzinfo=timezone.utc))

    from app.models.enums import TimelineEventType

    event = record_timeline_event(
        db_session, cluster_id=uuid.uuid4(), document=final,
        membership_type=IssueMembershipType.FOLLOW_UP, previous_document=proposed,
    )

    assert event.event_type == TimelineEventType.SUBSTANTIVE_CHANGE
    assert event.compared_to_document_id == proposed.id


def test_weak_signal_match_is_insufficient_comparison_data_not_guessed(db_session):
    """제목 유사도로만 연결된 경우, 실질적 변화 여부를 추측하지 않고 '비교 자료 부족'으로 표시해야 한다."""
    source = _make_source(db_session)
    doc1 = _make_doc(db_session, source, "Quantum Research Funding Notice", datetime(2024, 1, 1, tzinfo=timezone.utc))
    doc2 = _make_doc(db_session, source, "Quantum Research Funding Update", datetime(2024, 1, 10, tzinfo=timezone.utc))

    from app.models.enums import TimelineEventType

    event = record_timeline_event(
        db_session, cluster_id=uuid.uuid4(), document=doc2,
        membership_type=IssueMembershipType.DUPLICATE_REPORT, previous_document=doc1,
    )

    assert event.event_type == TimelineEventType.INSUFFICIENT_COMPARISON_DATA


def test_identical_title_repeat_is_no_substantive_change(db_session):
    source = _make_source(db_session)
    doc1 = _make_doc(db_session, source, "Routine Quarterly Report", datetime(2024, 1, 1, tzinfo=timezone.utc))
    doc2 = _make_doc(db_session, source, "Routine Quarterly Report", datetime(2024, 4, 1, tzinfo=timezone.utc))

    from app.models.enums import TimelineEventType

    event = record_timeline_event(
        db_session, cluster_id=uuid.uuid4(), document=doc2,
        membership_type=IssueMembershipType.FOLLOW_UP, previous_document=doc1,
    )

    assert event.event_type == TimelineEventType.NO_SUBSTANTIVE_CHANGE
