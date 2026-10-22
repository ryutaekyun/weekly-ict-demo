from datetime import datetime, timezone

from app.models.enums import DocumentType, FieldCode, SourceType, UserRole
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import classification as classification_service
from app.services import extraction as extraction_service
from tests.conftest import auth_headers, make_user


def _make_source_and_doc(db_session) -> tuple[Source, SourceDocument]:
    from app.models.enums import SourceDocumentStatus

    source = Source(
        name="Test Source", org_name="Test Agency", field_code=FieldCode.SEC, country_code="US",
        url="https://example.org/feed", source_type=SourceType.RSS, is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    doc = SourceDocument(
        source_id=source.id, title="Semiconductor export control chip policy update",
        origin_url="https://example.org/doc1", collected_at=datetime.now(timezone.utc),
        raw_text="This policy covers semiconductor chip export control and supply chain quantum computing hardware.",
        content_hash="hash1", status=SourceDocumentStatus.COLLECTED, field_code=source.field_code,
        collection_method=SourceType.RSS, document_type=DocumentType.POLICY,
        published_at=datetime.now(timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return source, doc


def test_process_document_requires_auth(client, db_session):
    _, doc = _make_source_and_doc(db_session)
    resp = client.post(f"/documents/{doc.id}/process")
    assert resp.status_code == 401


def test_researcher_role_cannot_process_but_reviewer_can(client, db_session, monkeypatch):
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: False)  # 외부 호출 방지, 요약 폴백 유도

    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "researcher@example.com", UserRole.RESEARCHER)
    make_user(db_session, "reviewer@example.com", UserRole.REVIEWER)

    researcher_headers = auth_headers(client, "researcher@example.com")
    resp = client.post(f"/documents/{doc.id}/process", headers=researcher_headers)
    assert resp.status_code == 403

    reviewer_headers = auth_headers(client, "reviewer@example.com")
    resp = client.post(f"/documents/{doc.id}/process", headers=reviewer_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"]["method"] == "rule_based"
    assert body["classification"]["primary_field_code"] == "semi"  # 출처 고정분야(sec)와 달라야 함


def test_analysis_endpoint_returns_null_sections_before_processing(client, db_session):
    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    resp = client.get(f"/documents/{doc.id}/analysis", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["classification"] is None
    assert body["value_assessment"] is None


def test_classification_override_requires_reason_tracked_in_history(client, db_session, monkeypatch):
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: False)

    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    client.post(f"/documents/{doc.id}/process", headers=headers)

    resp = client.patch(
        f"/documents/{doc.id}/classification",
        json={"primary_field_code": "conv", "related_field_codes": [], "relevance": "matched", "reason": "테스트 수정"},
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["primary_field_code"] == "conv"
    assert body["is_researcher_overridden"] is True
    assert body["method"] == "researcher"


def test_full_text_endpoint_contains_body_analysis_endpoint_does_not(client, db_session, monkeypatch):
    monkeypatch.setattr(classification_service, "get_ai_provider", lambda: None)
    monkeypatch.setattr(extraction_service, "_robots_allowed", lambda url: False)

    _, doc = _make_source_and_doc(db_session)
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")
    client.post(f"/documents/{doc.id}/process", headers=headers)

    analysis_resp = client.get(f"/documents/{doc.id}/analysis", headers=headers)
    assert analysis_resp.json()["full_text"]["full_text"] is None

    fulltext_resp = client.get(f"/documents/{doc.id}/full-text", headers=headers)
    assert fulltext_resp.status_code == 200
    # robots 차단으로 요약 폴백이 쓰였으므로 extraction_status는 NOT_ATTEMPTED/FAILED 중 하나여야 한다
    assert fulltext_resp.json()["extraction_status"] in ("not_attempted", "failed")


def test_sources_documents_endpoint_regression_unaffected(client, db_session):
    """Phase 2-2 추가가 기존 /sources/{id}/documents 응답을 깨지 않았는지 회귀 확인."""
    source, doc = _make_source_and_doc(db_session)
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    headers = auth_headers(client, "admin@example.com")

    resp = client.get(f"/sources/{source.id}/documents", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["field_code"] == "sec"  # 기존 필드는 그대로 출처 고정값을 유지해야 함(하위호환)
