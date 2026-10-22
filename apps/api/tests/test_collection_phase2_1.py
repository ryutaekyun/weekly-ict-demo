import httpx

from app.models.enums import (
    CollectionErrorType,
    DocumentType,
    FieldCode,
    SourceDocumentStatus,
    SourceType,
    UserRole,
)
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import collection as collection_service
from tests.conftest import auth_headers, make_user

FR_RESPONSE_V1 = {
    "results": [
        {
            "title": "Example Rule on Spectrum Allocation",
            "html_url": "https://www.federalregister.gov/d/2026-00001",
            "publication_date": "2026-01-15",
            "abstract": "An example abstract text.",
            "type": "RULE",
            "pdf_url": "https://www.federalregister.gov/d/2026-00001.pdf",
        }
    ]
}

FR_RESPONSE_V2_UPDATED = {
    "results": [
        {
            "title": "Example Rule on Spectrum Allocation",
            "html_url": "https://www.federalregister.gov/d/2026-00001",
            "publication_date": "2026-01-15",
            "abstract": "An example abstract text, REVISED with corrections.",
            "type": "RULE",
            "pdf_url": "https://www.federalregister.gov/d/2026-00001.pdf",
        }
    ]
}


def _make_api_source(db_session, url="https://www.federalregister.gov/api/v1/articles.json?x=1") -> Source:
    source = Source(
        name="Federal Register test",
        org_name="Test Agency",
        field_code=FieldCode.BCAST,
        country_code="US",
        url=url,
        source_type=SourceType.API,
        api_provider="federal_register",
        is_primary_source=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def _mock_json_response(monkeypatch, payload: dict):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return FakeResponse()

    monkeypatch.setattr(collection_service, "_http_client", lambda: FakeClient())


def test_federal_register_collector_inserts_normalized_document(db_session, monkeypatch):
    source = _make_api_source(db_session)
    _mock_json_response(monkeypatch, FR_RESPONSE_V1)

    run = collection_service.run_collection(db_session, source)

    assert run.status.value == "success"
    assert run.items_new == 1
    doc = db_session.query(SourceDocument).one()
    assert doc.title == "Example Rule on Spectrum Allocation"
    assert doc.origin_url == "https://www.federalregister.gov/d/2026-00001"
    assert doc.attachment_url.endswith(".pdf")
    assert doc.document_type == DocumentType.LAW
    assert doc.collection_method == SourceType.API
    assert doc.field_code == FieldCode.BCAST  # 이번 단계는 출처의 고정 분야를 그대로 사용
    assert doc.published_at.year == 2026
    assert doc.published_at.month == 1
    assert doc.status == SourceDocumentStatus.COLLECTED


def test_content_revision_is_tracked_as_updated_not_duplicate(db_session, monkeypatch):
    source = _make_api_source(db_session)
    _mock_json_response(monkeypatch, FR_RESPONSE_V1)
    collection_service.run_collection(db_session, source)
    original = db_session.query(SourceDocument).one()

    _mock_json_response(monkeypatch, FR_RESPONSE_V2_UPDATED)
    run2 = collection_service.run_collection(db_session, source)

    assert run2.items_updated == 1
    assert run2.items_new == 0
    assert db_session.query(SourceDocument).count() == 2

    revised = (
        db_session.query(SourceDocument)
        .filter(SourceDocument.id != original.id)
        .one()
    )
    assert revised.status == SourceDocumentStatus.UPDATED
    assert revised.previous_version_id == original.id
    assert "REVISED" in revised.raw_text


def test_unrelated_duplicate_content_from_different_url_is_flagged(db_session, monkeypatch):
    source = _make_api_source(db_session)
    _mock_json_response(monkeypatch, FR_RESPONSE_V1)
    collection_service.run_collection(db_session, source)
    original = db_session.query(SourceDocument).one()

    same_title_diff_url = {
        "results": [
            {
                **FR_RESPONSE_V1["results"][0],
                "html_url": "https://www.federalregister.gov/d/2026-99999",
            }
        ]
    }
    _mock_json_response(monkeypatch, same_title_diff_url)
    run2 = collection_service.run_collection(db_session, source)

    assert run2.items_duplicate == 1
    dup = db_session.query(SourceDocument).filter(SourceDocument.id != original.id).one()
    assert dup.status == SourceDocumentStatus.DUPLICATE
    assert dup.duplicate_of_id == original.id


def test_source_flagged_for_review_after_repeated_failures_not_deactivated(db_session, monkeypatch):
    source = _make_api_source(db_session)

    def raise_error(url=None):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", "https://example.org"))

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(collection_service, "_http_client", lambda: FakeClient())

    for _ in range(3):
        run = collection_service.run_collection(db_session, source)
        assert run.status.value == "failed"
        assert run.error_type == CollectionErrorType.CONNECTION_ERROR

    db_session.refresh(source)
    assert source.consecutive_failures == 3
    assert source.needs_review is True
    assert source.is_active is True  # 자동 비활성화하지 않는다


def test_admin_can_update_source_reviewer_cannot(client, db_session):
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    make_user(db_session, "reviewer@example.com", UserRole.REVIEWER)
    source = _make_api_source(db_session, url="https://www.federalregister.gov/api/v1/articles.json?x=2")

    reviewer_headers = auth_headers(client, "reviewer@example.com")
    resp = client.patch(f"/sources/{source.id}", json={"is_active": False}, headers=reviewer_headers)
    assert resp.status_code == 403

    admin_headers = auth_headers(client, "admin@example.com")
    resp = client.patch(
        f"/sources/{source.id}",
        json={"needs_review": False, "is_active": True},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["needs_review"] is False


def test_get_source_detail_includes_document_count_and_last_run(client, db_session, monkeypatch):
    make_user(db_session, "admin@example.com", UserRole.ADMIN)
    source = _make_api_source(db_session, url="https://www.federalregister.gov/api/v1/articles.json?x=3")
    _mock_json_response(monkeypatch, FR_RESPONSE_V1)
    collection_service.run_collection(db_session, source)

    headers = auth_headers(client, "admin@example.com")
    resp = client.get(f"/sources/{source.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["document_count"] == 1
    assert body["last_run_status"] == "success"
