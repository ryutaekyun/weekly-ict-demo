from datetime import datetime, timezone

from app.models.document_classification import DocumentClassification
from app.models.document_full_text import DocumentFullText
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
    UserRole,
)
from app.models.source import Source
from app.models.source_document import SourceDocument
from tests.conftest import auth_headers, make_user


def _make_full_doc(db_session, *, title, field_code, relevance=ClassificationRelevance.MATCHED, rating=UsageValueRating.GENERAL):
    source = Source(
        name="Federal Register", org_name="US Govt", field_code=FieldCode.SEMI, country_code="US",
        url="https://example.org/feed", source_type=SourceType.API, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    doc = SourceDocument(
        source_id=source.id, title=title, origin_url=f"https://example.org/{title[:20]}",
        collected_at=datetime.now(timezone.utc), raw_text="", content_hash=title,
        status=SourceDocumentStatus.COLLECTED, field_code=source.field_code, collection_method=SourceType.API,
        document_type=DocumentType.POLICY, published_at=datetime.now(timezone.utc), country_code="US",
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    db_session.add(DocumentClassification(
        document_id=doc.id, primary_field_code=field_code, relevance=relevance,
        method=ClassificationMethod.RULE_BASED, classified_at=datetime.now(timezone.utc),
    ))
    db_session.add(DocumentFullText(
        document_id=doc.id, full_text="본문", extraction_status=ExtractionStatus.SUCCESS,
        extraction_method=ExtractionMethod.HTML, char_count=2, extracted_at=datetime.now(timezone.utc),
    ))
    db_session.add(DocumentValueAssessment(
        document_id=doc.id, rating=rating, method=ClassificationMethod.RULE_BASED,
    ))
    db_session.commit()
    return source, doc


def test_document_list_requires_auth(client, db_session):
    resp = client.get("/documents")
    assert resp.status_code == 401


def test_document_list_filters_by_classification_field_not_source_field(client, db_session):
    """분야 필터가 출처 고정분야가 아니라 document_classifications.primary_field_code를 따라야 한다."""
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    _make_full_doc(db_session, title="AI policy update one", field_code=FieldCode.AI)
    _make_full_doc(db_session, title="Semiconductor export rule", field_code=FieldCode.SEMI)

    resp = client.get("/documents", params={"field_code": "ai"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["primary_field_code"] == "ai"
    assert body["items"][0]["source_org_name"] == "US Govt"


def test_document_list_pagination_and_keyword_search(client, db_session):
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    for i in range(5):
        _make_full_doc(db_session, title=f"Quantum computing update {i}", field_code=FieldCode.SEMI)

    resp = client.get("/documents", params={"page": 1, "page_size": 2}, headers=headers)
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2

    resp = client.get("/documents", params={"q": "Quantum"}, headers=headers)
    assert resp.json()["total"] == 5

    resp = client.get("/documents", params={"q": "NoSuchKeyword"}, headers=headers)
    assert resp.json()["total"] == 0


def test_document_meta_endpoint_returns_single_document(client, db_session):
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")
    _, doc = _make_full_doc(db_session, title="Single doc test", field_code=FieldCode.NET)

    resp = client.get(f"/documents/{doc.id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["title"] == "Single doc test"
    assert resp.json()["primary_field_code"] == "net"
    assert resp.json()["extraction_status"] == "success"
    assert resp.json()["value_rating"] == "general"


def test_dashboard_summary_counts_match_real_rows(client, db_session):
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    _make_full_doc(db_session, title="Matched AI doc", field_code=FieldCode.AI)
    _make_full_doc(db_session, title="Low relevance doc", field_code=None, relevance=ClassificationRelevance.LOW_RELEVANCE)

    resp = client.get("/dashboard/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_documents"] == 2
    assert body["matched_documents"] == 1
    assert body["low_relevance_documents"] == 1
    assert body["extraction_success"] == 2
    assert any(f["field_code"] == "ai" and f["document_count"] == 1 for f in body["by_field"])


def test_dashboard_summary_requires_auth(client, db_session):
    resp = client.get("/dashboard/summary")
    assert resp.status_code == 401
