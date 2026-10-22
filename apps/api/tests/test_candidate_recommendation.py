from datetime import datetime, timedelta, timezone

from app.models.document_full_text import DocumentFullText
from app.models.document_value_assessment import DocumentValueAssessment
from app.models.enums import (
    ClassificationMethod,
    ClusterReviewStatus,
    DocumentType,
    ExtractionMethod,
    ExtractionStatus,
    FieldCode,
    IssueMembershipType,
    SourceDocumentStatus,
    SourceType,
    UsageValueRating,
    UserRole,
)
from app.models.issue_cluster import IssueCluster
from app.models.issue_cluster_document import IssueClusterDocument
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.models.user import User
from app.services.candidate_recommendation import run_candidate_recommendation
from tests.conftest import make_user


def _make_source(db_session) -> Source:
    source = Source(
        name="Test", org_name="Test Agency", field_code=FieldCode.AI, country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True, reliability_tier=1,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _make_cluster_with_doc(db_session, source, *, rating: UsageValueRating | None, published_at=None, title="Test Issue"):
    doc = SourceDocument(
        source_id=source.id, title=title, origin_url=f"https://example.org/{title[:15]}",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash=title,
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code, collection_method=SourceType.RSS,
        document_type=DocumentType.POLICY, published_at=published_at or datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    db_session.add(DocumentFullText(
        document_id=doc.id, full_text="x" * 5000, extraction_status=ExtractionStatus.SUCCESS,
        extraction_method=ExtractionMethod.HTML, char_count=5000, extracted_at=datetime.now(timezone.utc),
    ))
    if rating is not None:
        db_session.add(DocumentValueAssessment(
            document_id=doc.id, rating=rating, method=ClassificationMethod.RULE_BASED,
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


def test_low_relevance_only_cluster_is_not_recommended(db_session):
    user = make_user(db_session, "admin@example.com", UserRole.ADMIN)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(db_session, source, rating=UsageValueRating.LOW_RELEVANCE)

    result = run_candidate_recommendation(db_session, cluster, created_by_user_id=user.id)

    assert result is None


def test_domestic_relevance_skipped_not_zero_filled(db_session):
    from app.models.enums import UserRole

    user = make_user(db_session, "admin2@example.com", UserRole.ADMIN)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(db_session, source, rating=UsageValueRating.PRIORITY)

    result = run_candidate_recommendation(db_session, cluster, created_by_user_id=user.id)

    assert result is not None
    candidate, score = result
    assert score.domestic_relevance_score is None
    import json
    reasoning = json.loads(score.reasoning_json)
    assert "domestic_relevance" in reasoning["skipped_criteria"]
    # 평가 보류 항목이 있어도 나머지 항목으로 재정규화된 총점은 계산돼야 한다
    assert score.total_score is not None


def test_recent_priority_document_scores_higher_than_old_general(db_session):
    from app.models.enums import UserRole

    user = make_user(db_session, "admin3@example.com", UserRole.ADMIN)
    source = _make_source(db_session)
    recent_cluster, _ = _make_cluster_with_doc(
        db_session, source, rating=UsageValueRating.PRIORITY,
        published_at=datetime.now(timezone.utc) - timedelta(days=2), title="Recent Priority Issue",
    )
    old_cluster, _ = _make_cluster_with_doc(
        db_session, source, rating=UsageValueRating.GENERAL,
        published_at=datetime.now(timezone.utc) - timedelta(days=200), title="Old General Issue",
    )

    recent_result = run_candidate_recommendation(db_session, recent_cluster, created_by_user_id=user.id)
    old_result = run_candidate_recommendation(db_session, old_cluster, created_by_user_id=user.id)

    assert recent_result[1].total_score > old_result[1].total_score


def test_duplicate_title_lowers_novelty_score(db_session):
    from app.models.candidate import Candidate
    from app.models.enums import CandidateStatus, UserRole

    user = make_user(db_session, "admin4@example.com", UserRole.ADMIN)
    source = _make_source(db_session)
    cluster, doc = _make_cluster_with_doc(
        db_session, source, rating=UsageValueRating.GENERAL, title="Semiconductor Export Control Policy Update"
    )
    db_session.add(Candidate(
        field_code=FieldCode.AI, title="Semiconductor Export Control Policy Update Announcement",
        status=CandidateStatus.FINAL, created_by_user_id=user.id,
    ))
    db_session.commit()

    result = run_candidate_recommendation(db_session, cluster, created_by_user_id=user.id)

    assert result is not None
    _, score = result
    assert score.novelty_score < 100.0
