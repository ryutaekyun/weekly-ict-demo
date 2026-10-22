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
    SourceDocumentStatus,
    SourceType,
    UserRole,
)
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import issue_analysis as issue_analysis_service
from tests.conftest import auth_headers, make_user


def _make_source_and_doc(db_session, title="Test Policy Announcement"):
    source = Source(
        name="Test", org_name="Test Agency", field_code=FieldCode.AI, country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    doc = SourceDocument(
        source_id=source.id, title=title, origin_url="https://example.org/doc1",
        collected_at=datetime.now(timezone.utc), raw_text="summary text",
        content_hash="h1", status=SourceDocumentStatus.COLLECTED, field_code=source.field_code,
        collection_method=SourceType.RSS, document_type=DocumentType.POLICY,
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    db_session.add(DocumentClassification(
        document_id=doc.id, primary_field_code=FieldCode.AI, relevance=ClassificationRelevance.MATCHED,
        method=ClassificationMethod.RULE_BASED, classified_at=datetime.now(timezone.utc),
    ))
    db_session.add(DocumentFullText(
        document_id=doc.id, full_text="Full text content here.", extraction_status=ExtractionStatus.SUCCESS,
        extraction_method=ExtractionMethod.HTML, char_count=24, extracted_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    return source, doc


def test_cluster_requires_auth(client, db_session):
    _, doc = _make_source_and_doc(db_session)
    resp = client.post(f"/issues/cluster/{doc.id}")
    assert resp.status_code == 401


def test_researcher_cannot_cluster_but_reviewer_can(client, db_session, monkeypatch):
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    make_user(db_session, "reviewer@example.com", UserRole.REVIEWER)

    r_headers = auth_headers(client, "researcher@example.com")
    resp = client.post(f"/issues/cluster/{doc.id}", headers=r_headers)
    assert resp.status_code == 403

    rv_headers = auth_headers(client, "reviewer@example.com")
    resp = client.post(f"/issues/cluster/{doc.id}", headers=rv_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_count"] == 1


def test_issue_detail_after_analysis(client, db_session, monkeypatch):
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    cluster_resp = client.post(f"/issues/cluster/{doc.id}", headers=headers)
    cluster_id = cluster_resp.json()["id"]

    analyze_resp = client.post(f"/issues/{cluster_id}/analyze", headers=headers)
    assert analyze_resp.status_code == 200
    assert analyze_resp.json()["generated_by"] == "rule_based"

    detail_resp = client.get(f"/issues/{cluster_id}", headers=headers)
    assert detail_resp.status_code == 200
    body = detail_resp.json()
    assert len(body["members"]) == 1
    assert len(body["timeline"]) == 1
    assert body["timeline"][0]["event_type"] == "new_issue"


def test_scoring_config_default_and_admin_only_update(client, db_session):
    make_user(db_session, "admin2@example.com", UserRole.ADMIN)
    make_user(db_session, "reviewer2@example.com", UserRole.REVIEWER)

    admin_headers = auth_headers(client, "admin2@example.com")
    resp = client.get("/issues/scoring/config", headers=admin_headers)
    assert resp.status_code == 200
    assert abs(sum(resp.json().values()) - 1.0) < 1e-6

    reviewer_headers = auth_headers(client, "reviewer2@example.com")
    resp = client.patch("/issues/scoring/config", json={"policy_impact_weight": 0.5}, headers=reviewer_headers)
    assert resp.status_code == 403

    resp = client.patch("/issues/scoring/config", json={"policy_impact_weight": 0.5}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["policy_impact_weight"] == 0.5


def test_manual_split_creates_independent_cluster(client, db_session, monkeypatch):
    monkeypatch.setattr(issue_analysis_service, "get_ai_provider", lambda: None)
    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "admin3@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin3@example.com")

    cluster_resp = client.post(f"/issues/cluster/{doc.id}", headers=headers)
    original_cluster_id = cluster_resp.json()["id"]

    split_resp = client.post(
        "/issues/split", json={"document_id": str(doc.id), "reason": "테스트 분리"}, headers=headers
    )
    assert split_resp.status_code == 200
    new_cluster_id = split_resp.json()["id"]
    assert new_cluster_id != original_cluster_id
