"""Phase 4-2 — 수집 작업(Job)·중복·버전·SSRF 방어·예약·정보원 관리 API."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.collection_job import CollectionJob
from app.models.enums import CollectionJobStatus, FieldCode, SourceType, UserRole
from app.models.source import Source
from app.models.source_document import SourceDocument
from app.services import collection as collection_service
from app.services import collection_jobs, url_guard
from tests.conftest import auth_headers, make_user

ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>t</title>
  <entry>
    <id>http://arxiv.org/abs/2601.00001v1</id>
    <title>Large language model agents for spectrum management</title>
    <summary>We study large language model based agents for spectrum allocation and 5G networks.</summary>
    <published>2026-01-02T00:00:00Z</published><updated>2026-01-02T00:00:00Z>
    <link href="http://arxiv.org/abs/2601.00001v1"/>
  </entry>
</feed>""".replace("Z>", "Z</updated>")


def _source(db, **kw):
    s = Source(name=kw.pop("name", "arXiv test"), org_name="arXiv", field_code=FieldCode.AI, country_code="INT", url=kw.pop("url", "https://export.arxiv.org/api/query?search_query=cat:cs.AI"),
               source_type=kw.pop("source_type", SourceType.API), api_provider=kw.pop("api_provider", "arxiv_api"), is_primary_source=True, **kw)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _factory(db_session):
    class _S:  # execute_job 이 close() 해도 테스트 세션은 유지한다
        def __init__(self): self.s = db_session
        def __getattr__(self, n): return getattr(self.s, n)
        def close(self): pass
    return lambda: _S()


def test_arxiv_api_dedup_and_versioning(client, db_session, monkeypatch):
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    src = _source(db_session)
    feed = {"v": ATOM}
    monkeypatch.setattr(collection_service, "fetch_raw_feed", lambda url: feed["v"].encode())
    r1 = collection_service.run_collection(db_session, src)
    assert (r1.items_new, r1.items_duplicate, r1.items_updated) == (1, 0, 0)
    doc = db_session.query(SourceDocument).one()
    assert doc.external_id == "arxiv:2601.00001" and doc.origin_url == "https://arxiv.org/abs/2601.00001" and doc.language == "en" and doc.version_no == 1
    r2 = collection_service.run_collection(db_session, src)  # 같은 자료 재수집 → 중복(새 행 없음)
    assert (r2.items_new, r2.items_duplicate, r2.items_updated) == (0, 1, 0)
    assert db_session.query(SourceDocument).count() == 1
    feed["v"] = ATOM.replace("spectrum allocation", "spectrum allocation REVISED")  # 원문 수정 → 새 버전
    r3 = collection_service.run_collection(db_session, src)
    assert (r3.items_new, r3.items_updated) == (0, 1)
    docs = db_session.query(SourceDocument).order_by(SourceDocument.version_no).all()
    assert [d.version_no for d in docs] == [1, 2] and [d.is_latest for d in docs] == [False, True]
    assert docs[1].previous_version_id == docs[0].id and docs[0].published_at is not None  # 이전 버전 보존, 발표일 유지
    assert docs[1].document_updated_at is not None


def test_job_runs_classifies_and_flags_changed_source(client, db_session, monkeypatch):
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    src = _source(db_session)
    monkeypatch.setattr(collection_service, "fetch_raw_feed", lambda url: ATOM.encode())
    job, created = collection_jobs.enqueue_job(db_session, src, trigger="manual")
    assert created and job.active_key == str(src.id)
    again, created2 = collection_jobs.enqueue_job(db_session, src, trigger="manual")  # 연속 클릭 → 같은 작업
    assert not created2 and again.id == job.id
    # 전문 추출 단계의 외부 접속은 막고 제목·초록 분류만 돌린다
    import app.services.pipeline as pipeline
    monkeypatch.setattr(pipeline, "run_extraction", lambda db, d: (_ for _ in ()).throw(RuntimeError("no network in test")))
    collection_jobs.execute_job(_factory(db_session), job.id)
    db_session.expire_all()
    j = db_session.get(CollectionJob, job.id)
    assert j.status == CollectionJobStatus.SUCCEEDED and j.items_new == 1 and j.active_key is None
    assert db_session.get(Source, src.id).access_status == "ok"
    assert collection_jobs.active_job_for(db_session, src.id) is None  # 끝난 뒤에는 다시 수집 가능


def test_failed_job_records_reason_and_access_status(client, db_session, monkeypatch):
    src = _source(db_session)

    def boom(url):
        import httpx
        req = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("403", request=req, response=httpx.Response(403, request=req))

    monkeypatch.setattr(collection_service, "fetch_raw_feed", boom)
    job, _ = collection_jobs.enqueue_job(db_session, src, trigger="manual")
    collection_jobs.execute_job(_factory(db_session), job.id)
    db_session.expire_all()
    j = db_session.get(CollectionJob, job.id)
    s = db_session.get(Source, src.id)
    assert j.status == CollectionJobStatus.FAILED and j.error_type == "http_4xx" and j.active_key is None
    assert s.access_status == "blocked" and "우회하지 않았습니다" in s.access_note and s.consecutive_failures == 1


def test_stale_running_job_is_recovered_and_cancel_works(client, db_session):
    src = _source(db_session)
    job, _ = collection_jobs.enqueue_job(db_session, src, trigger="schedule")
    assert collection_jobs.claim_job(db_session, job.id)
    assert not collection_jobs.claim_job(db_session, job.id)  # 이미 가져간 작업은 다시 가져갈 수 없다(중복 실행 방지)
    job = db_session.get(CollectionJob, job.id)
    job.heartbeat_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db_session.commit()
    assert collection_jobs.recover_stale_jobs(db_session) == 1
    db_session.refresh(job)
    assert job.status == CollectionJobStatus.INTERRUPTED and job.active_key is None
    j2, c = collection_jobs.enqueue_job(db_session, src, trigger="manual")
    assert c
    collection_jobs.request_cancel(db_session, j2)
    db_session.refresh(j2)
    assert j2.status == CollectionJobStatus.CANCELLED and j2.active_key is None


def test_schedule_tick_runs_due_sources_only(client, db_session, monkeypatch):
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    due = _source(db_session, name="due", interval_minutes=60)
    fresh = _source(db_session, name="fresh", interval_minutes=60)
    fresh.last_attempted_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    off = _source(db_session, name="off", interval_minutes=0)
    db_session.commit()
    monkeypatch.setattr(collection_service, "fetch_raw_feed", lambda url: ATOM.encode())
    import app.services.pipeline as pipeline
    monkeypatch.setattr(pipeline, "run_extraction", lambda db, d: (_ for _ in ()).throw(RuntimeError("no network")))
    res = collection_jobs.schedule_tick(_factory(db_session))
    assert res["enqueued"] == 1 and len(res["ran"]) == 1
    jobs = db_session.query(CollectionJob).all()
    assert [j.source_id for j in jobs] == [due.id] and jobs[0].trigger == "schedule"
    assert not collection_jobs.is_due(off, datetime.now(timezone.utc)) and not collection_jobs.is_due(fresh, datetime.now(timezone.utc))


def test_url_guard_blocks_internal_and_bad_urls(monkeypatch):
    for bad in ("file:///etc/passwd", "ftp://example.com/x", "http://user:pw@example.com/", "https://example.com:22/"):
        with pytest.raises(url_guard.UnsafeURLError):
            url_guard.assert_safe_url(bad)
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))])
    with pytest.raises(url_guard.UnsafeURLError):
        url_guard.assert_safe_url("https://internal.example.com/")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 80))])
    with pytest.raises(url_guard.UnsafeURLError):
        url_guard.assert_safe_url("http://localhost.example/")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    url_guard.assert_safe_url("https://www.example.com/feed")  # 공인 주소는 통과


def test_source_admin_api_create_test_collect_history(client, db_session, monkeypatch):
    make_user(db_session, "adm@example.com", UserRole.ADMIN)
    make_user(db_session, "res@example.com", UserRole.RESEARCHER)
    h = auth_headers(client, "adm@example.com")
    bad = client.post("/sources", json={"name": "x", "org_name": "x", "field_code": "ai", "url": "ftp://x.example/feed", "source_type": "rss"}, headers=h)
    assert bad.status_code == 400
    bad2 = client.post("/sources", json={"name": "x", "org_name": "x", "field_code": "ai", "url": "https://x.example/api", "source_type": "api", "api_provider": "nope"}, headers=h)
    assert bad2.status_code == 400
    monkeypatch.setattr(collection_service, "fetch_raw_feed", lambda url: ATOM.encode())
    tc = client.post("/sources/test-connection", json={"url": "https://export.arxiv.org/api/query?x=1", "source_type": "api", "api_provider": "arxiv_api"}, headers=h).json()
    assert tc["ok"] and tc["found"] == 1 and tc["sample"][0]["external_id"] == "arxiv:2601.00001"
    ok = client.post("/sources", json={"name": "arXiv API test", "org_name": "arXiv", "field_code": "ai", "url": "https://export.arxiv.org/api/query?x=1", "source_type": "api",
                                       "api_provider": "arxiv_api", "interval_minutes": 120}, headers=h)
    assert ok.status_code == 201 and ok.json()["interval_minutes"] == 120 and ok.json()["access_label"] == "미검증"
    sid = ok.json()["id"]
    started = client.post(f"/sources/{sid}/collect", headers=h)
    assert started.status_code == 202 and started.json()["job"]["status"] == "queued" and started.json()["already_running"] is False
    again = client.post(f"/sources/{sid}/collect", headers=h).json()
    assert again["already_running"] is True and again["job"]["id"] == started.json()["job"]["id"]
    assert client.get(f"/sources/jobs/{started.json()['job']['id']}", headers=h).json()["stage"] == "대기 중"
    # 연구원은 정보원 등록·수정 불가, 전체 상태는 조회 가능
    rh = auth_headers(client, "res@example.com")
    assert client.post("/sources", json={"name": "x", "org_name": "x", "field_code": "ai", "url": "https://x.example/a", "source_type": "rss"}, headers=rh).status_code == 403
    assert client.post(f"/sources/{sid}/collect", headers=rh).status_code == 403
    st = client.get("/collection/status", headers=rh).json()
    assert set(st) >= {"last_collected_at", "new_last_24h", "to_review", "failed_sources", "running_jobs"} and len(st["running_jobs"]) == 1
    # 비활성화(삭제 대신) + 이력 보존
    assert client.patch(f"/sources/{sid}", json={"is_active": False, "url": "https://export.arxiv.org/api/query?x=2"}, headers=h).status_code == 200
    hist = client.get(f"/sources/{sid}/history", headers=h).json()
    assert {x["action"] for x in hist} >= {"source.create", "source.update", "source.collect"}
    assert client.post(f"/sources/{sid}/collect", headers=h).status_code == 400


def test_html_and_pdf_and_metadata_sources(client, db_session, monkeypatch):
    html = b'<html><body><a href="/docs/rule-2026-01.html">Spectrum rule 2026 final notice</a><a href="/about">About</a><a href="https://other.example/x">External long link text here</a></body></html>'

    class R:
        def __init__(self, content): self.content = content
        def raise_for_status(self): pass

    class C:
        def __init__(self, content): self.content = content
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return R(self.content)

    monkeypatch.setattr(url_guard, "robots_allowed", lambda url, ua: True)
    h = _source(db_session, name="html", url="https://agency.example/news", source_type=SourceType.HTML, api_provider=None)
    monkeypatch.setattr(collection_service, "_http_client", lambda: C(html))
    entries = collection_service._fetch_entries(h)
    assert [e.link for e in entries] == ["https://agency.example/docs/rule-2026-01.html"]  # 같은 사이트 링크만, 짧은 메뉴 링크 제외
    p = _source(db_session, name="pdf", url="https://agency.example/a.pdf", source_type=SourceType.PDF, api_provider=None, config_json=json.dumps({"title": "Official PDF"}))
    monkeypatch.setattr(collection_service, "_http_client", lambda: C(b"%PDF-1.4 fake"))
    pe = collection_service._fetch_entries(p)
    assert pe[0].title == "Official PDF" and pe[0].summary.startswith("PDF 파일 해시")
    monkeypatch.setattr(collection_service, "_http_client", lambda: C(b"<html>not pdf</html>"))
    with pytest.raises(ValueError):
        collection_service._fetch_entries(p)
    # robots.txt 거부는 우회하지 않고 오류 유형으로 기록
    monkeypatch.setattr(url_guard, "robots_allowed", lambda url, ua: False)
    monkeypatch.setattr(collection_service, "_http_client", lambda: C(html))
    run = collection_service.run_collection(db_session, h)
    assert run.status.value == "failed" and run.error_type.value == "robots_disallowed"
    assert db_session.get(Source, h.id).access_status == "blocked"


def test_normalize_url_and_language():
    n = collection_service.normalize_url
    assert n("http://Example.com/a/b/?utm_source=x&id=1#frag") == "https://example.com/a/b?id=1"
    assert collection_service.detect_language("인공지능 정책 동향") == "ko"
    assert collection_service.detect_language("人工知能に関する政策のお知らせ") == "ja"
    assert collection_service.detect_language("人工智能政策通知公告内容") == "zh"
    assert collection_service.detect_language("Artificial intelligence policy") == "en"
