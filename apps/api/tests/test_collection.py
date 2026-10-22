import httpx
import pytest

from app.models.enums import CollectionRunStatus, FieldCode, SourceDocumentStatus, SourceType
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import collection as collection_service

SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>5G spectrum allocation announced</title>
      <link>https://example.org/articles/5g-spectrum</link>
      <published>Mon, 02 Feb 2026 09:00:00 GMT</published>
      <description>Summary text</description>
    </item>
    <item>
      <title>Second article</title>
      <link>https://example.org/articles/second</link>
      <published>Mon, 02 Feb 2026 10:00:00 GMT</published>
    </item>
  </channel>
</rss>
"""


def _make_source(db_session) -> Source:
    source = Source(
        name="Sample Source",
        org_name="Sample Org",
        field_code=FieldCode.NET,
        url="https://example.org/feed.xml",
        source_type=SourceType.RSS,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


def test_run_collection_inserts_new_documents(db_session, monkeypatch):
    source = _make_source(db_session)
    monkeypatch.setattr(collection_service, "fetch_raw_feed", lambda url: SAMPLE_FEED)

    run = collection_service.run_collection(db_session, source)

    assert run.status == CollectionRunStatus.SUCCESS
    assert run.items_found == 2
    assert run.items_new == 2
    assert run.items_duplicate == 0

    docs = db_session.query(SourceDocument).all()
    assert len(docs) == 2
    assert all(d.status == SourceDocumentStatus.COLLECTED for d in docs)
    assert {d.origin_url for d in docs} == {
        "https://example.org/articles/5g-spectrum",
        "https://example.org/articles/second",
    }


def test_run_collection_dedupes_by_origin_url_on_rerun(db_session, monkeypatch):
    source = _make_source(db_session)
    monkeypatch.setattr(collection_service, "fetch_raw_feed", lambda url: SAMPLE_FEED)

    collection_service.run_collection(db_session, source)
    second_run = collection_service.run_collection(db_session, source)

    assert second_run.items_new == 0
    assert second_run.items_duplicate == 2
    assert db_session.query(SourceDocument).count() == 2  # 중복 삽입되지 않음


def test_run_collection_records_failure_on_fetch_error(db_session, monkeypatch):
    source = _make_source(db_session)

    def raise_error(url):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(collection_service, "fetch_raw_feed", raise_error)

    run = collection_service.run_collection(db_session, source)

    assert run.status == CollectionRunStatus.FAILED
    assert "ConnectError" in run.error_message
    assert run.retry_count == 1
    assert db_session.query(SourceDocument).count() == 0
