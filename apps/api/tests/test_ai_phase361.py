"""Phase 3-6.1 — AI 문장 원문 변경 재검토, 의미 불일치 탐지, 삽입 위치·취소, 공급자 오류 분류, 비용·사용량 (모두 모의 응답/모의 HTTP 기반 — 실제 AI 호출 없음)."""

import json
from datetime import date, datetime, timezone

import httpx
import pytest

from app.models.ai_analysis import AIAnalysis, AIInsertion, AIPriceSetting
from app.models.document_full_text import DocumentFullText
from app.models.enums import FieldCode, ManuscriptStatus, UserRole
from app.models.manuscript import Manuscript
from app.services import ai_analysis_service as svc
from app.services import ai_evidence, ai_service
from tests.conftest import auth_headers, make_user
from tests.test_ai_phase36 import FMVSS_A, FMVSS_B, FakeProvider, cluster_with, doc_payload, item, run, use
from tests.test_card_news import (  # noqa: F401  (autouse 픽스처 재사용)
    _report_with_manuscript, _skip_rendering_unless_marked,
)
from tests.test_phase35 import make_doc


@pytest.fixture
def researcher(client, db_session):
    make_user(db_session, "ai361@example.com", UserRole.RESEARCHER, "연구원")
    return auth_headers(client, "ai361@example.com")


Q_EFFECTIVE = "The final rule takes effect on February 18, 2025."
FMVSS_A_CHANGED = FMVSS_A.replace("February 18, 2025", "March 20, 2025")


def draft_for(client, db_session, researcher, monkeypatch, sections):
    doc = make_doc(db_session, title="FMVSS 305a final rule", field=FieldCode.AI, url="https://example.org/fmvss", days_ago=30, full_text=FMVSS_A)
    cluster = cluster_with(db_session, [doc])
    cand = client.post("/candidates", headers=researcher, json={"field_code": "ai", "title": "후보", "issue_cluster_id": str(cluster.id), "source_document_id": str(doc.id)}).json()
    use(monkeypatch, FakeProvider(doc_payload(sections)))
    out = run(client, researcher, "draft", cand["id"]).json()
    return doc, cand, out


def change_source(db_session, doc, new_text):
    ft = db_session.query(DocumentFullText).filter_by(document_id=doc.id).one()
    ft.full_text, ft.content_hash = new_text, "hash-" + str(abs(hash(new_text)))
    db_session.commit()


# ------------------------------------------------ A·B: 삽입 후 원문 변경 → 재검토, 기존 원고·승인본·출력본 보존 (FMVSS 305a 시행일 변경) ----
def test_fmvss_flow_inserted_ai_sentence_is_flagged_when_source_changes_and_reaches_report_and_card_news(client, db_session, researcher, monkeypatch):
    mid, rid = _report_with_manuscript(client, researcher, verify=True)
    doc, cand, out = draft_for(client, db_session, researcher, monkeypatch, {"background": [
        item("최종 규정은 2025.2.18.부터 시행됨", [("D1", Q_EFFECTIVE)])]})
    claim = out["sections"][0]["claims"] if out["sections"][0]["key"] == "background" else next(s for s in out["sections"] if s["key"] == "background")["claims"]
    ms = client.get(f"/manuscripts/{mid}", headers=researcher).json()
    body_before = ms["body_json"]
    sent = next(s for s in client.get(f"/card-news/report-sentences/{rid}", headers=researcher).json()["sentences"] if "제정안을 공고함" in s["sentence"])
    cn = client.post("/card-news", headers=researcher, json={"title": "AI 연계", "template_key": "A", "source_type": "report", "source_report_id": rid,
                                                               "selections": [{"manuscript_id": mid, "sentence": sent["sentence"]}]}).json()
    ins = client.post(f"/ai/analyses/{out['id']}/insert", headers=researcher, json={"manuscript_id": mid, "claim_ids": [claim[0]["id"]], "lock_version": ms["lock_version"],
                                                                                     "edited_texts": {claim[0]["id"]: "최종 규정은 2025.2.18.부터 시행됨(연구원 확인)"}})
    assert ins.status_code == 200, ins.text
    rows = client.get(f"/ai/manuscripts/{mid}/insertions", headers=researcher).json()
    assert len(rows) == 1 and rows[0]["needs_review"] is False and rows[0]["edited_by_researcher"] is True
    assert rows[0]["ai_text"] != rows[0]["final_text"] and rows[0]["source_hash_at_insert"]  # AI 원문과 연구원 최종 문장, 삽입 시점의 원문 버전을 구분해 보존
    assert client.get(f"/reports/{rid}", headers=researcher).json()["blocking"] is not None

    # 원문이 바뀌었다(시행일 연기 반영) — 후속 규정 등록과 별개로, 이미 삽입된 AI 문장이 재검토 대상으로 표시된다
    change_source(db_session, doc, FMVSS_A_CHANGED)
    row = client.get(f"/ai/manuscripts/{mid}/insertions", headers=researcher).json()[0]
    assert row["needs_review"] is True
    ch = row["change"]
    assert ch["old_quote_still_in_source"] is False and "2025-02-18" in ch["removed_facts"] and "2025-03-20" in ch["added_facts"]
    assert ch["stale_in_sentence"] == ["2025-02-18"] and ch["new_sentence"] and "March 20, 2025" in ch["new_sentence"]  # 변경 전후 차이 표시
    detail = client.get(f"/manuscripts/{mid}", headers=researcher).json()
    assert detail["needs_reexamination"]["flagged"] and "AI가 제안해 삽입한 문장" in detail["needs_reexamination"]["reason"]
    assert detail["body_json"] != body_before and "연구원 확인" in detail["body_json"]  # 삽입은 됐지만 원문 변경이 원고를 자동 수정하지 않았다
    after_change = client.get(f"/manuscripts/{mid}", headers=researcher).json()
    assert after_change["body"] == detail["body"]
    # 보고서·카드뉴스에도 재검토 상태가 전달된다
    rep = client.get(f"/reports/{rid}", headers=researcher).json()
    assert any(b["code"] == "followup_pending" and "근거 원문 변경" in b["message"] for b in rep["blocking"])
    assert any(b["code"] == "followup_pending" for b in client.get(f"/card-news/{cn['id']}", headers=researcher).json()["blocking"])
    # 검증 완료 각주는 재확인 전까지 '검증 완료'로 세지 않는다
    assert detail["footnote_verification_verified"] < detail["footnote_verification_total"]
    # 최종 승인 차단
    m = db_session.get(Manuscript, __import__("uuid").UUID(mid))
    m.status = ManuscriptStatus.REVIEW_REQUESTED
    db_session.commit()
    make_user(db_session, "ai361-ap@example.com", UserRole.APPROVER)
    assert client.post(f"/manuscripts/{mid}/approve", headers=auth_headers(client, "ai361-ap@example.com"), json={"comment": "x"}).status_code == 409

    # 재검토: 이전 날짜가 원고에 남아 있으면 '영향 없음'·'수정 반영'으로 닫을 수 없다
    iid = row["id"]
    r = client.post(f"/ai/insertions/{iid}/review", headers=researcher, json={"resolution": "no_impact", "note": "영향 없음으로 봄"})
    assert r.status_code == 422 and "2025-02-18" in r.json()["detail"]
    assert client.post(f"/ai/insertions/{iid}/review", headers=researcher, json={"resolution": "updated", "note": ""}).status_code == 422  # 사유 필수
    assert client.post(f"/ai/insertions/{iid}/review", headers=researcher, json={"resolution": "needs_check", "note": "관보 원문 재확인 필요"}).status_code == 200
    assert client.get(f"/ai/manuscripts/{mid}/insertions", headers=researcher).json()[0]["needs_review"] is True  # 추가 확인 필요는 해소가 아니다
    # 연구원이 문장을 고쳐 새 버전으로 저장 → 수정 반영 완료
    fixed = json.loads(client.get(f"/manuscripts/{mid}", headers=researcher).json()["body_json"])
    for n in fixed["content"]:
        for t in n.get("content", []):
            if "2025.2.18." in t.get("text", ""):
                t["text"] = t["text"].replace("2025.2.18.", "2025.3.20.")
    cur = client.get(f"/manuscripts/{mid}", headers=researcher).json()
    saved = client.patch(f"/manuscripts/{mid}", headers=researcher, json={"body_json": json.dumps(fixed, ensure_ascii=False), "body": cur["body"].replace("2025.2.18.", "2025.3.20."),
                                                                           "lock_version": cur["lock_version"], "change_note": "시행일 변경 반영"})
    assert saved.status_code == 200
    done = client.post(f"/ai/insertions/{iid}/review", headers=researcher, json={"resolution": "updated", "note": "시행일을 3월 20일로 고쳐 반영함"})
    assert done.status_code == 200 and done.json()["needs_review"] is False
    hist = done.json()["history"]
    assert [h["resolution"] for h in hist] == ["needs_check", "updated"] and hist[-1]["reviewer_id"] and hist[-1]["reviewed_at"] and hist[-1]["reviewed_source_hash"]
    assert not any(b["code"] == "followup_pending" for b in client.get(f"/reports/{rid}", headers=researcher).json()["blocking"])
    # 과거 버전(삽입 직후)은 삭제되지 않고 남아 있다
    versions = client.get(f"/manuscripts/{mid}/versions", headers=researcher).json()
    assert len(versions) >= 2
    # 원문이 다시 바뀌면 다시 표시된다
    change_source(db_session, doc, FMVSS_A_CHANGED.replace("March 20, 2025", "April 1, 2025"))
    assert client.get(f"/ai/manuscripts/{mid}/insertions", headers=researcher).json()[0]["needs_review"] is True


def test_no_impact_review_when_change_does_not_touch_the_cited_sentence(client, db_session, researcher, monkeypatch):
    doc, cand, out = draft_for(client, db_session, researcher, monkeypatch, {"background": [item("최종 규정은 2025.2.18.부터 시행됨", [("D1", Q_EFFECTIVE)])]})
    ms = client.post("/manuscripts", headers=researcher, json={"manuscript_type": "key_issue", "title": "원고", "candidate_id": cand["id"]}).json()
    cid = next(s for s in out["sections"] if s["key"] == "background")["claims"][0]["id"]
    assert client.post(f"/ai/analyses/{out['id']}/insert", headers=researcher, json={"manuscript_id": ms["id"], "claim_ids": [cid], "lock_version": ms["lock_version"]}).status_code == 200
    change_source(db_session, doc, FMVSS_A + "\n\nAn unrelated appendix paragraph was added to the notice after publication.")  # 인용 문장은 그대로
    row = client.get(f"/ai/manuscripts/{ms['id']}/insertions", headers=researcher).json()[0]
    assert row["needs_review"] and row["change"]["old_quote_still_in_source"] is True and row["change"]["stale_in_sentence"] == []
    ok = client.post(f"/ai/insertions/{row['id']}/review", headers=researcher, json={"resolution": "no_impact", "note": "인용 문장은 그대로이고 부록만 추가됨"})
    assert ok.status_code == 200 and ok.json()["needs_review"] is False
    removed = client.post(f"/ai/insertions/{row['id']}/review", headers=researcher, json={"resolution": "removed", "note": "문장을 삭제하기로 함"})
    assert removed.status_code == 200 and removed.json()["status"] == "removed"


# ------------------------------------------------ E·F: 삽입 위치·취소·저장 충돌 ----
def test_insert_at_cursor_under_heading_or_end_marks_ai_text_and_undo_is_safe(client, db_session, researcher, monkeypatch):
    doc, cand, out = draft_for(client, db_session, researcher, monkeypatch, {"background": [
        item("최종 규정은 2025.2.18.부터 시행됨", [("D1", Q_EFFECTIVE)]), item("수소 방출 한도는 0.5 g임", [("D1", "The standard limits emissions of hydrogen to 0.5 g during the crash test and covers vehicles over 4,536 kg.")])]})
    ms = client.post("/manuscripts", headers=researcher, json={"manuscript_type": "key_issue", "title": "원고", "candidate_id": cand["id"]}).json()
    body = {"type": "doc", "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "1. 추진 경과"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "첫 문단임"}]},
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "2. 시사점"}]},
        {"type": "paragraph", "content": [{"type": "text", "text": "마지막 문단임"}]}]}
    saved = client.patch(f"/manuscripts/{ms['id']}", headers=researcher, json={"body_json": json.dumps(body, ensure_ascii=False), "body": "x", "lock_version": ms["lock_version"]}).json()
    claims = next(s for s in out["sections"] if s["key"] == "background")["claims"]

    def texts():
        return [n["content"][0]["text"] for n in json.loads(client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()["body_json"])["content"]]

    # 지정 소제목 아래
    r1 = client.post(f"/ai/analyses/{out['id']}/insert", headers=researcher, json={"manuscript_id": ms["id"], "claim_ids": [claims[0]["id"]], "lock_version": saved["lock_version"],
                                                                                     "position": {"mode": "after_heading", "heading_text": "2. 시사점"}})
    assert r1.status_code == 200 and texts() == ["1. 추진 경과", "첫 문단임", "2. 시사점", "최종 규정은 2025.2.18.부터 시행됨", "마지막 문단임"]
    # 현재 커서(문단 인덱스 1) 뒤
    r2 = client.post(f"/ai/analyses/{out['id']}/insert", headers=researcher, json={"manuscript_id": ms["id"], "claim_ids": [claims[1]["id"]], "lock_version": r1.json()["lock_version"],
                                                                                     "position": {"mode": "after_index", "index": 1}})
    assert r2.status_code == 200 and texts()[:3] == ["1. 추진 경과", "첫 문단임", "수소 방출 한도는 0.5 g임"]
    # 잘못된 위치·없는 소제목은 거부하고 원고를 바꾸지 않는다
    before = client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()
    for pos in ({"mode": "after_heading", "heading_text": "없는 제목"}, {"mode": "after_index", "index": 99}):
        bad = client.post(f"/ai/analyses/{out['id']}/insert", headers=researcher, json={"manuscript_id": ms["id"], "claim_ids": [claims[0]["id"]], "lock_version": r2.json()["lock_version"], "position": pos})
        assert bad.status_code == 422
    assert client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()["body_json"] == before["body_json"]
    # 표시: 삽입 문단에는 AI 마크와 미검증 각주 마크가 붙는다
    marks = [m["type"] for n in json.loads(before["body_json"])["content"] for t in n.get("content", []) for m in t.get("marks", [])]
    assert marks.count("aiInsert") == 2 and marks.count("footnoteMark") == 2
    # F: 저장 충돌 — 오래된 lock_version이면 409이고 원고는 손실 없이 그대로다
    stale = client.post(f"/ai/analyses/{out['id']}/insert", headers=researcher, json={"manuscript_id": ms["id"], "claim_ids": [claims[0]["id"]], "lock_version": saved["lock_version"]})
    assert stale.status_code == 409
    assert client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()["body_json"] == before["body_json"]
    assert db_session.query(AIInsertion).filter_by(manuscript_id=__import__("uuid").UUID(ms["id"])).count() == 2  # 실패한 삽입은 기록되지 않는다
    # 삽입 취소: 고치지 않은 AI 문단은 지우고 미검증 각주도 함께 제거 / 연구원이 고친 문단은 지우지 않는다
    rows = client.get(f"/ai/manuscripts/{ms['id']}/insertions", headers=researcher).json()
    lv = client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()["lock_version"]
    u1 = client.post(f"/ai/insertions/{rows[0]['id']}/undo", headers=researcher, json={"lock_version": lv})
    assert u1.status_code == 200 and "최종 규정은 2025.2.18.부터 시행됨" not in texts()
    assert len(client.get(f"/manuscripts/{ms['id']}/footnotes", headers=researcher).json()) == 1
    cur = client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()
    edited = json.loads(cur["body_json"])
    for n in edited["content"]:
        for t in n.get("content", []):
            if t["text"].startswith("수소"):
                t["text"] += " (연구원이 덧붙임)"
    client.patch(f"/manuscripts/{ms['id']}", headers=researcher, json={"body_json": json.dumps(edited, ensure_ascii=False), "body": "x", "lock_version": cur["lock_version"]})
    lv2 = client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()["lock_version"]
    assert client.post(f"/ai/insertions/{rows[1]['id']}/undo", headers=researcher, json={"lock_version": lv2}).status_code == 409
    assert client.post(f"/ai/insertions/{rows[0]['id']}/undo", headers=researcher, json={"lock_version": lv2}).status_code == 409  # 이미 취소됨


# ------------------------------------------------ C·D: 의미 불일치 가능성 / 잘못된 문서 연결 ----
def test_semantic_checks_date_role_unit_comparator_negation_and_wrong_document():
    q = "The final rule takes effect on February 18, 2025. Manufacturers must document the information by December 22, 2025."
    assert ai_evidence.semantic_flags("시행일은 2025.2.18.임", q) == []
    assert "역할이 다름" in ai_evidence.semantic_flags("준수 시한은 2025.2.18.임", q)[0]  # 시행일 vs 준수 시한 혼동
    assert "역할이 다름" in ai_evidence.semantic_flags("발표일은 2025.12.22.임", q)[0] or ai_evidence.semantic_flags("시행일은 2025.12.22.임", q)
    assert "단위가 다름" in ai_evidence.semantic_flags("한도는 0.5 kg임", "limits hydrogen to 0.5 g")[0]
    assert "수량 조건" in ai_evidence.semantic_flags("4,536 kg 이하 차량에 적용됨", "covers vehicles over 4,536 kg")[0]
    assert "부정" in ai_evidence.semantic_flags("업계가 연기를 요청하지 않음", "commenters asked for a longer transition period")[0]
    assert ai_evidence.semantic_flags("시행일은 2025.2.18.이며 한도는 0.5 g임", "takes effect on February 18, 2025 and limits hydrogen to 0.5 g") == []


def test_semantic_risk_and_wrong_document_links_are_reported_with_notes(client, db_session, researcher, monkeypatch):
    a = make_doc(db_session, title="Doc A", field=FieldCode.AI, days_ago=40, full_text=FMVSS_A)
    b = make_doc(db_session, title="Doc B", field=FieldCode.AI, days_ago=2, full_text=FMVSS_B)
    cluster = cluster_with(db_session, [a, b])
    qa_deadline = "Manufacturers must document emergency response information by December 22, 2025."
    qb = "The effective date is now March 20, 2025 following the petitions received from vehicle manufacturers in February 2025."
    use(monkeypatch, FakeProvider(doc_payload({"changes": [
        item("비상대응정보 문서화 시행일은 2025.12.22.임", [("D1", qa_deadline)]),  # 준수 시한을 시행일로 오인
        item("연기된 시행일은 2025.3.20.임", [("D1", qb)]),  # 발췌문은 D2에 있는데 D1에 연결
        item("수소 방출 한도는 0.5 g이며 4,536 kg 이하 차량에 적용됨", [("D1", "The standard limits emissions of hydrogen to 0.5 g during the crash test and covers vehicles over 4,536 kg.")]),
        item("2025.2.18.부터 시행되며 업계가 요청하지 않음", [("D1", Q_EFFECTIVE)]),
        item("2025년 12월 22일에 시행됨", [("D1", Q_EFFECTIVE)]),  # 값은 원문 다른 위치에 있음
    ]})))
    claims = next(s for s in run(client, researcher, "issue", cluster.id).json()["sections"] if s["key"] == "changes")["claims"]
    assert [c["evidence_status"] for c in claims] == ["semantic_risk", "not_found", "semantic_risk", "semantic_risk", "value_mismatch"]
    assert "역할이 다름" in claims[0]["check_note"] and "잘못된 문서" in claims[1]["check_note"] and "D2" in claims[1]["check_note"]
    assert "수량 조건" in claims[2]["check_note"] and "부정" in claims[3]["check_note"] and "다른 위치" in claims[4]["check_note"]
    c0 = claims[0]["id"]
    assert client.post(f"/ai/claims/{c0}/review", headers=researcher, json={"action": "verify"}).status_code == 422  # 의미 위험 문장도 사유 없이 검증 완료 불가


# ------------------------------------------------ H: 공급자별 오류 분류(모의 HTTP) ----
def _resp(status, body=None, text=None):
    return httpx.Response(status, json=body) if body is not None else httpx.Response(status, text=text or "")


@pytest.mark.parametrize("status,body,exc", [
    (401, {"error": {"message": "invalid x-api-key"}}, ai_service.AIAuthError),
    (403, {"error": {"message": "permission denied"}}, ai_service.AIAuthError),
    (404, {"error": {"message": "model: foo"}}, ai_service.AIModelError),
    (400, {"error": {"message": "model 'x' does not exist"}}, ai_service.AIModelError),
    (429, {"error": {"message": "rate limit"}}, ai_service.AIRateLimitError),
    (400, {"error": {"message": "prompt is too long: 300000 tokens > 200000 maximum"}}, ai_service.AIContextError),
    (500, {"error": {"message": "internal"}}, ai_service.AIServerError),
    (529, {"error": {"message": "overloaded"}}, ai_service.AIServerError),
])
@pytest.mark.parametrize("prov", ["anthropic", "openai"])
def test_provider_http_errors_are_classified_with_exact_codes(monkeypatch, prov, status, body, exc):
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(status, body))
    p = ai_service.AnthropicProvider("k", "claude-sonnet-5-5") if prov == "anthropic" else ai_service.OpenAIProvider("k", "m")
    with pytest.raises(exc) as ei:
        p.complete_json("s", "u")
    assert ei.value.code and ei.value.http_status == status and "k" not in str(ei.value).split(":")[0][-1:]  # 키는 메시지에 포함하지 않는다


def test_provider_timeout_bad_json_truncation_and_usage_extraction(monkeypatch):
    p = ai_service.AnthropicProvider("k", "claude-sonnet-5-5")

    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(httpx, "request", boom)
    with pytest.raises(ai_service.AITimeoutError):
        p.complete_json("s", "u")
    ok = {"content": [{"type": "thinking", "thinking": "..."}, {"type": "text", "text": '{"sections": []}'}], "usage": {"input_tokens": 1234, "output_tokens": 56}, "stop_reason": "end_turn"}
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, ok))
    r = p.complete_json("s", "u")
    assert (r.input_tokens, r.output_tokens, r.text) == (1234, 56, '{"sections": []}')  # 사고 블록은 본문에 섞이지 않고 토큰은 응답값 사용
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {**ok, "stop_reason": "max_tokens"}))
    with pytest.raises(ai_service.AITruncatedError) as ei:
        p.complete_json("s", "u")
    assert ei.value.usage == (1234, 56)  # 잘린 응답도 사용 토큰은 남긴다
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, text="<html>not json</html>"))
    with pytest.raises(ai_service.AIBadResponseError):
        p.complete_json("s", "u")
    o = ai_service.OpenAIProvider("k", "m")
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"choices": [{"message": {"content": "{}"}, "finish_reason": "length"}], "usage": {"prompt_tokens": 9, "completion_tokens": 8}}))
    with pytest.raises(ai_service.AITruncatedError) as ei2:
        o.complete_json("s", "u")
    assert ei2.value.usage == (9, 8)
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 9, "completion_tokens": 8}}))
    assert (o.complete_json("s", "u").input_tokens, o.complete_json("s", "u").output_tokens) == (9, 8)
    with pytest.raises(ai_service.AIBadResponseError):
        ai_service.extract_json_object("no json here")


def test_default_models_are_not_guessed(monkeypatch):
    for k in ("AI_PROVIDER", "AI_MODEL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert ai_service.get_ai_provider() is None and any("AI_MODEL" in g for g in ai_service.configuration_gaps())  # OpenAI는 기본 모델을 추측하지 않는다
    monkeypatch.setenv("AI_MODEL", "my-model")
    assert ai_service.get_ai_provider().model == "my-model"
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.delenv("AI_MODEL")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert ai_service.get_ai_provider().model == "claude-sonnet-5-5"  # 공식 모델 문서(2026-10-27)에 있는 ID


def test_diagnostics_never_reports_success_without_key_and_checks_model_list_when_key_exists(client, db_session, monkeypatch):
    make_user(db_session, "ai361-adm@example.com", UserRole.ADMIN)
    h = auth_headers(client, "ai361-adm@example.com")
    use(monkeypatch, None)
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    d = client.post("/ai/diagnostics", headers=h).json()
    assert d["connection"] == "not_configured" and d["verified"] is False and "연결 미검증" in d["message"]
    st = client.get("/ai/status", headers=h).json()
    assert st["connection"] == "not_configured" and st["configured"] is False
    p = ai_service.AnthropicProvider("k", "claude-sonnet-5-5")
    use(monkeypatch, p)
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"data": [{"id": "claude-sonnet-5-5"}, {"id": "claude-haiku-5-5"}]}))
    import app.api.ai as ai_api
    monkeypatch.setattr(ai_api.ai_service, "get_ai_provider", lambda: p)
    ok = client.post("/ai/diagnostics", headers=h).json()
    assert ok["connection"] == "ok" and ok["verified"] and "분석 호출은 하지 않았습니다" in ok["message"]
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"data": [{"id": "other"}]}))
    assert client.post("/ai/diagnostics", headers=h).json()["connection"] == "model_unavailable"
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(401, {"error": {"message": "bad key"}}))
    bad = client.post("/ai/diagnostics", headers=h).json()
    assert bad["connection"] == "failed" and bad["error_code"] == "auth_error" and bad["verified"] is False
    make_user(db_session, "ai361-res@example.com", UserRole.RESEARCHER)
    assert client.post("/ai/diagnostics", headers=auth_headers(client, "ai361-res@example.com")).status_code == 403


# ------------------------------------------------ H·I: 실패 상태·취소 의미·중단·원문 변경·가격표·사용량 ----
def test_failed_calls_record_exact_code_tokens_and_leave_existing_manuscript_and_rule_results_untouched(client, db_session, researcher, monkeypatch):
    doc = make_doc(db_session, title="Doc", field=FieldCode.AI, full_text=FMVSS_A)
    ms = client.post("/manuscripts", headers=researcher, json={"manuscript_type": "key_issue", "title": "원고"}).json()
    saved = client.patch(f"/manuscripts/{ms['id']}", headers=researcher, json={"body_json": json.dumps({"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "기존 문장임"}]}]}),
                                                                              "body": "기존 문장임", "lock_version": ms["lock_version"]}).json()
    db_session.add(AIPriceSetting(provider="anthropic", model="claude-sonnet-5-5", input_per_mtok=2.0, output_per_mtok=10.0, effective_date=date(2026, 10, 27), version=1, is_active=True))
    db_session.commit()
    p = ai_service.AnthropicProvider("k", "claude-sonnet-5-5")
    use(monkeypatch, p)
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"content": [{"type": "text", "text": "{"}], "usage": {"input_tokens": 3000, "output_tokens": 12000}, "stop_reason": "max_tokens"}))
    out = run(client, researcher, "document", doc.id).json()
    assert out["status"] == "failed" and out["error_code"] == "truncated" and "잘려" in out["error_message"] and out["provider_request_sent"] is True
    assert out["input_tokens"] == 3000 and out["output_tokens"] == 12000 and out["actual_cost_usd"] == pytest.approx(0.126) and "v1" in out["pricing_version"]
    for status, code in ((401, "auth_error"), (429, "rate_limited"), (500, "provider_5xx"), (404, "model_error")):
        monkeypatch.setattr(httpx, "request", lambda *a, _s=status, **k: _resp(_s, {"error": {"message": "x"}}))
        r = run(client, researcher, "document", doc.id, force=True).json()
        assert r["status"] == "failed" and r["error_code"] == code, (status, r)
    def slow(*a, **k):
        raise httpx.ReadTimeout("t")
    monkeypatch.setattr(httpx, "request", slow)
    assert run(client, researcher, "document", doc.id, force=True).json()["error_code"] == "timeout"
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"content": [{"type": "text", "text": "not json"}], "usage": {"input_tokens": 5, "output_tokens": 2}, "stop_reason": "end_turn"}))
    assert run(client, researcher, "document", doc.id, force=True).json()["error_code"] == "bad_response"
    # 실패해도 기존 원고·규칙 기반 화면은 그대로
    after = client.get(f"/manuscripts/{ms['id']}", headers=researcher).json()
    assert after["body_json"] == saved["body_json"] and after["lock_version"] == saved["lock_version"]
    assert client.get(f"/documents/{doc.id}", headers=researcher).status_code == 200
    # 응답이 근거 없는 사실만 담은 경우(근거자료 없는 응답): 성공 호출이지만 검증은 '근거 부족'
    monkeypatch.setattr(httpx, "request", lambda *a, **k: _resp(200, {"content": [{"type": "text", "text": json.dumps({"sections": [{"key": "summary", "items": [{"text": "근거 없는 주장임", "type": "fact", "evidence": []}]}]})}],
                                                                       "usage": {"input_tokens": 10, "output_tokens": 5}, "stop_reason": "end_turn"}))
    nb = run(client, researcher, "document", doc.id, force=True).json()
    assert nb["status"] == "completed" and nb["verification_status"] == "insufficient"
    # 사용량: 사용자별 집계·실패 포함, 실제 청구액이 아니라 계산값임을 표시
    u = client.get("/ai/usage?days=1", headers=researcher).json()
    assert u["requests"] >= 7 and u["provider_requests_sent"] >= 7 and u["failed_or_cancelled"] >= 6 and "청구금액이 아닙니다" in u["cost_note"]


def test_cancel_is_db_only_after_request_sent_and_stale_running_is_marked_interrupted(client, db_session, researcher, monkeypatch):
    doc = make_doc(db_session, title="Doc", field=FieldCode.AI, full_text=FMVSS_A)

    class Canceller(FakeProvider):
        def complete_json(self, *a, **k):
            for row in db_session.query(AIAnalysis).filter_by(status="running"):
                row.cancelled = True
            db_session.commit()
            return super().complete_json(*a, **k)

    use(monkeypatch, Canceller(doc_payload({"summary": [item("요지", [("D1", Q_EFFECTIVE)])]})))
    c = run(client, researcher, "document", doc.id).json()
    assert c["status"] == "cancelled" and c["provider_request_sent"] is True and "비용이 발생했을 수 있" in c["cancel_note"] and c["input_tokens"] == 1200  # '취소=비용 없음'이 아니다
    # 브라우저 종료 등으로 오래 running인 요청은 '중단됨'으로 정리된다
    from datetime import timedelta
    old = AIAnalysis(kind="document", target_type="document", target_id=doc.id, requested_by_user_id=db_session.query(AIAnalysis).first().requested_by_user_id, status="running",
                     prompt_version="x", request_key="k-stale", source_fingerprint="", input_documents_json="[]", provider_request_sent=True,
                     started_at=datetime.now(timezone.utc) - timedelta(minutes=30))
    db_session.add(old)
    db_session.commit()
    got = client.get(f"/ai/analyses/{old.id}", headers=researcher).json()
    assert got["status"] == "failed" and got["error_code"] == "interrupted" and "비용이 발생했을 수 있" in got["error_message"]


def test_source_change_during_analysis_is_flagged_for_reanalysis(client, db_session, researcher, monkeypatch):
    doc = make_doc(db_session, title="Doc", field=FieldCode.AI, full_text=FMVSS_A)

    class Changer(FakeProvider):
        def complete_json(self, *a, **k):
            change_source(db_session, doc, FMVSS_A_CHANGED)
            return super().complete_json(*a, **k)

    use(monkeypatch, Changer(doc_payload({"summary": [item("요지", [("D1", Q_EFFECTIVE)])]})))
    out = run(client, researcher, "document", doc.id).json()
    assert out["source_changed_during_run"] is True and any("분석 도중 원문이 변경" in n for n in out["notes"])


def test_pricing_is_admin_managed_versioned_and_unknown_price_is_never_zero(client, db_session, researcher, monkeypatch):
    make_user(db_session, "ai361-adm2@example.com", UserRole.ADMIN)
    adm = auth_headers(client, "ai361-adm2@example.com")
    body = {"provider": "anthropic", "model": "claude-sonnet-5-5", "input_per_mtok": 2.0, "output_per_mtok": 10.0, "effective_date": "2026-10-27", "source_note": "공식 가격표 확인"}
    assert client.put("/ai/pricing", headers=researcher, json=body).status_code == 403
    assert client.put("/ai/pricing", headers=adm, json=body).json()["version"] == 1
    assert client.put("/ai/pricing", headers=adm, json={**body, "input_per_mtok": 2.5}).json()["version"] == 2
    rows = client.get("/ai/pricing", headers=researcher).json()
    assert [r["version"] for r in rows] == [2, 1] and [r["is_active"] for r in rows] == [True, False]  # 이전 단가는 보존
    doc = make_doc(db_session, title="Doc", field=FieldCode.AI, full_text=FMVSS_A)
    use(monkeypatch, ai_service.AnthropicProvider("k", "claude-sonnet-5-5"))
    est = client.post("/ai/estimate", headers=researcher, json={"kind": "document", "target_id": str(doc.id)}).json()
    assert "v2" in est["pricing_version"] and "추정" in est["price_note"] or "추정" in est["price_note"]
    use(monkeypatch, ai_service.AnthropicProvider("k", "unpriced-model"))
    assert client.post("/ai/estimate", headers=researcher, json={"kind": "document", "target_id": str(doc.id)}).json()["est_cost_usd"] is None
    assert client.get("/ai/usage?scope=all", headers=researcher).status_code == 403  # 전체 사용량은 승인권자·관리자만
