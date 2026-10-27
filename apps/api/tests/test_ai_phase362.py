"""Phase 3-6.2A — 첫 실제 호출 안전장치(관리자 1건 승인·예산 상한·자동 재시도 금지), 키 보호, 응답 스키마 검증, 품질 평가. 실제 AI 호출 없음."""

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from app.models.ai_analysis import AIAnalysis, AICallApproval, AIPriceSetting
from app.models.enums import FieldCode, UserRole
from app.services import ai_analysis_service as svc
from app.services import ai_service
from tests.conftest import auth_headers, make_user
from tests.test_ai_phase36 import FMVSS_A, FakeProvider, doc_payload, item, run, use
from tests.test_ai_phase361 import patch_http
from tests.test_phase35 import make_doc

Q = "The final rule takes effect on February 18, 2025."
GOOD = doc_payload({"summary": [item("최종 규정은 2025.2.18.부터 시행됨", [("D1", Q)])]})


@pytest.fixture
def env(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_REQUIRE_APPROVAL", "1")  # 실제 공급자 게이트 켬
    make_user(db_session, "g-res@example.com", UserRole.RESEARCHER, "연구원")
    make_user(db_session, "g-adm@example.com", UserRole.ADMIN, "관리자")
    db_session.add(AIPriceSetting(provider="anthropic", model="fake-model-1", input_per_mtok=2.0, output_per_mtok=10.0, effective_date=date(2026, 10, 27), version=1, is_active=True))
    db_session.commit()
    return {"res": auth_headers(client, "g-res@example.com"), "adm": auth_headers(client, "g-adm@example.com"),
            "doc": make_doc(db_session, title="FMVSS", field=FieldCode.AI, full_text=FMVSS_A)}


def approve(client, env, **over):
    body = {"kind": "document", "target_id": str(env["doc"].id), "max_cost_usd": 0.5, "valid_minutes": 30, "note": "첫 실호출 승인"}
    body.update(over)
    return client.post("/ai/approvals", headers=env["adm"], json=body)


def test_real_call_requires_admin_approval_and_provider_is_not_called_without_it(client, db_session, env, monkeypatch):
    fake = use(monkeypatch, FakeProvider(GOOD))
    est = client.post("/ai/estimate", headers=env["res"], json={"kind": "document", "target_id": str(env["doc"].id)}).json()
    assert est["approval_required"] is True and est["approval"] is None
    r = run(client, env["res"], "document", env["doc"].id)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "approval_required" and fake.calls == 0
    assert db_session.query(AIAnalysis).count() == 0  # 호출도 기록도 없다
    assert client.post("/ai/approvals", headers=env["res"], json={"kind": "document", "target_id": str(env["doc"].id), "max_cost_usd": 0.5}).status_code == 403  # 승인은 관리자만
    assert client.get("/ai/status", headers=env["res"]).json()["require_approval"] is True


def test_approval_is_one_shot_budget_capped_and_failure_does_not_allow_automatic_retry(client, db_session, env, monkeypatch):
    fake = use(monkeypatch, FakeProvider(GOOD))
    assert approve(client, env, max_cost_usd=0.0001).status_code == 422  # 예상 비용보다 작은 상한은 승인 단계에서 거부
    a = approve(client, env)
    assert a.status_code == 200, a.text
    est = client.post("/ai/estimate", headers=env["res"], json={"kind": "document", "target_id": str(env["doc"].id)}).json()
    assert est["approval"]["id"] == a.json()["id"] and est["approval"]["max_cost_usd"] == 0.5
    ok = run(client, env["res"], "document", env["doc"].id)
    assert ok.status_code == 200 and fake.calls == 1
    row = db_session.get(AICallApproval, uuid.UUID(a.json()["id"]))
    assert row.used_at is not None and str(row.used_analysis_id) == ok.json()["id"]  # 승인은 호출 직전에 소멸
    again = run(client, env["res"], "document", env["doc"].id, force=True)
    assert again.status_code == 403 and fake.calls == 1  # 같은 승인으로 다시 호출 불가
    # 실패한 호출도 승인을 소모한다 → 새 승인 없이는 재시도되지 않는다
    use(monkeypatch, FakeProvider(error=ai_service.AIRateLimitError("429")))
    assert approve(client, env).status_code == 200
    failed = run(client, env["res"], "document", env["doc"].id, force=True).json()
    assert failed["status"] == "failed" and failed["error_code"] == "rate_limited"
    retry = run(client, env["res"], "document", env["doc"].id, force=True)
    assert retry.status_code == 403 and retry.json()["detail"]["code"] == "approval_required"
    # 다른 대상·만료·취소된 승인은 쓸 수 없다
    other = make_doc(db_session, title="Other", field=FieldCode.AI, full_text=FMVSS_A + " more text")
    assert run(client, env["res"], "document", other.id).status_code == 403
    fresh = approve(client, env).json()
    r = db_session.get(AICallApproval, uuid.UUID(fresh["id"]))
    r.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    assert run(client, env["res"], "document", env["doc"].id, force=True).status_code == 403
    again2 = approve(client, env).json()
    assert client.delete(f"/ai/approvals/{again2['id']}", headers=env["adm"]).status_code == 200
    assert run(client, env["res"], "document", env["doc"].id, force=True).status_code == 403
    assert len(client.get("/ai/approvals", headers=env["adm"]).json()) >= 4


def test_cost_cap_and_unknown_price_block_before_the_call(client, db_session, env, monkeypatch):
    fake = use(monkeypatch, FakeProvider(GOOD))
    approve(client, env)
    monkeypatch.setenv("AI_MAX_COST_PER_REQUEST_USD", "0.000001")  # 요청당 전역 상한
    r = run(client, env["res"], "document", env["doc"].id)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "budget_exceeded" and fake.calls == 0
    est = client.post("/ai/estimate", headers=env["res"], json={"kind": "document", "target_id": str(env["doc"].id)}).json()
    assert any("상한" in b for b in est["blockers"])
    monkeypatch.delenv("AI_MAX_COST_PER_REQUEST_USD")
    db_session.query(AIPriceSetting).delete()
    db_session.commit()  # 단가 미설정 → 승인 생성·호출 모두 차단
    unpriced_approval = approve(client, env)
    assert unpriced_approval.status_code == 422 and "단가" in unpriced_approval.text
    unpriced = run(client, env["res"], "document", env["doc"].id)
    assert unpriced.status_code == 409 and unpriced.json()["detail"]["code"] == "price_unknown" and fake.calls == 0


def test_mock_provider_needs_no_approval(client, db_session, env, monkeypatch):
    class M(FakeProvider):
        name = "mock"

    use(monkeypatch, M(GOOD))
    assert run(client, env["res"], "document", env["doc"].id).status_code == 200


def test_api_key_never_appears_in_errors_raw_responses_status_or_logs(client, db_session, env, monkeypatch):
    key = "sk-ant-test-0123456789abcdefghij"
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    assert key not in ai_service.redact_secrets(f"boom {key} boom") and "[REDACTED]" in ai_service.redact_secrets(f"x-api-key: {key}")
    assert "[REDACTED]" in ai_service.redact_secrets("token sk-proj-abcdefghijklmnopqrstu")
    p = ai_service.AnthropicProvider(key, "fake-model-1")
    use(monkeypatch, p)
    assert approve(client, env).status_code == 200
    patch_http(monkeypatch, lambda *a, **k: httpx.Response(401, json={"error": {"message": f"invalid x-api-key {key}"}}))
    out = run(client, env["res"], "document", env["doc"].id).json()
    assert out["error_code"] == "auth_error" and key not in json.dumps(out) and "[REDACTED]" in out["error_message"]
    row = db_session.query(AIAnalysis).one()
    assert key not in (row.error_message or "") and key not in (row.raw_response_text or "")
    assert key not in json.dumps(client.get("/ai/status", headers=env["res"]).json())
    assert approve(client, env).status_code == 200
    body = {"content": [{"type": "text", "text": json.dumps(GOOD) + f" leak {key}"}], "usage": {"input_tokens": 10, "output_tokens": 5}, "stop_reason": "end_turn"}
    patch_http(monkeypatch, lambda *a, **k: httpx.Response(200, json=body))
    ok = run(client, env["res"], "document", env["doc"].id, force=True).json()
    assert ok["status"] == "completed"
    raw = db_session.query(AIAnalysis).filter_by(status="completed").one().raw_response_text
    assert raw and "[REDACTED]" in raw and key not in raw and '"sections"' in raw  # 응답 원문은 저장하되 키는 지운다


def test_response_schema_validation_and_raw_response_storage(client, db_session, env, monkeypatch):
    monkeypatch.setenv("AI_REQUIRE_APPROVAL", "0")
    for payload in ({"nothing": 1}, {"sections": "x"}, {"sections": [{"items": []}]}):
        use(monkeypatch, FakeProvider(payload))
        out = run(client, env["res"], "document", env["doc"].id, force=True).json()
        assert out["status"] == "failed" and out["error_code"] == "bad_response" and "스키마" in out["error_message"]
    partial = {"sections": [{"key": "summary", "items": [{"type": "fact", "evidence": []}, {"text": "형식 미지정 사실임", "type": "weird", "evidence": [{"doc": "D1", "quote": Q}]}]},
                             {"key": "mystery", "items": []}], "insufficient": False, "notes": []}
    use(monkeypatch, FakeProvider(partial))
    ok = run(client, env["res"], "document", env["doc"].id, force=True).json()
    joined = " ".join(ok["notes"])
    assert ok["status"] == "completed" and "text가 없어 제외" in joined and "type이 올바르지 않아" in joined and "알 수 없는 섹션" in joined
    claims = next(s for s in ok["sections"] if s["key"] == "summary")["claims"]
    assert len(claims) == 1 and claims[0]["claim_type"] == "fact" and claims[0]["evidence_status"] == "found"
    assert db_session.query(AIAnalysis).filter_by(status="completed").one().raw_response_text


def test_anthropic_request_shape_has_no_thinking_field_and_structured_output_is_opt_in(monkeypatch):
    sent = {}

    def fake(method, url, **kw):
        sent.clear()
        sent.update(kw["json"])
        return httpx.Response(200, json={"content": [{"type": "text", "text": "{}"}], "usage": {"input_tokens": 1, "output_tokens": 1}, "stop_reason": "end_turn"})

    monkeypatch.setattr(httpx, "request", fake)
    p = ai_service.AnthropicProvider("k", "claude-sonnet-5-5")
    monkeypatch.delenv("AI_STRUCTURED_OUTPUT", raising=False)
    p.complete_json("sys", "usr", max_tokens=100, json_schema=svc.RESPONSE_SCHEMA)
    assert set(sent) == {"model", "max_tokens", "system", "messages"} and "thinking" not in sent  # Sonnet 5.5는 thinking 기본 적응형, "disabled"는 400
    monkeypatch.setenv("AI_STRUCTURED_OUTPUT", "1")
    p.complete_json("sys", "usr", max_tokens=100, json_schema=svc.RESPONSE_SCHEMA)
    assert sent["output_config"]["format"]["type"] == "json_schema" and sent["output_config"]["format"]["schema"]["additionalProperties"] is False


def test_quality_evaluation_requires_all_criteria_and_never_mixes_mock_with_real(client, db_session, env, monkeypatch):
    monkeypatch.setenv("AI_REQUIRE_APPROVAL", "0")
    scores = {k: "ok" for k in svc.EVAL_CRITERIA}
    use(monkeypatch, FakeProvider(doc_payload({"summary": [item("요지", [("D1", Q)]), item("근거 없음")]})))
    a_real = run(client, env["res"], "document", env["doc"].id).json()

    class M(FakeProvider):
        name = "mock"

    use(monkeypatch, M(GOOD))
    a_mock = run(client, env["res"], "document", env["doc"].id, force=True).json()
    assert client.post(f"/ai/analyses/{a_real['id']}/evaluation", headers=env["res"], json={"scores": {"c1_summary": "ok"}}).status_code == 422
    assert client.post(f"/ai/analyses/{a_real['id']}/evaluation", headers=env["res"], json={"scores": {**scores, "c2_values": "great"}}).status_code == 422
    ok = client.post(f"/ai/analyses/{a_real['id']}/evaluation", headers=env["res"], json={"scores": {**scores, "c4_evidence": "bad"}, "semantic_mismatch_cases": 1, "wrong_source_cases": 2, "notes": "근거 없는 문장 1건"})
    assert ok.status_code == 200 and ok.json()["is_mock"] is False
    assert client.post(f"/ai/analyses/{a_mock['id']}/evaluation", headers=env["res"], json={"scores": scores}).json()["is_mock"] is True
    s = client.get("/ai/evaluation-summary", headers=env["res"]).json()
    assert s["real"]["evaluations"] == 1 and s["mock"]["evaluations"] == 1  # 합산하지 않는다
    assert s["real"]["criteria"]["c4_evidence"]["bad"] == 1 and s["real"]["wrong_source_cases"] == 2 and s["real"]["facts"] == 2 and s["real"]["facts_without_valid_evidence"] == 1
    assert s["mock"]["criteria"]["c4_evidence"]["ok"] == 1 and s["mock"]["wrong_source_cases"] == 0 and "합산하지 않습니다" in s["note"]
    assert len(client.get(f"/ai/analyses/{a_real['id']}/evaluations", headers=env["res"]).json()) == 1
    use(monkeypatch, FakeProvider(error=ai_service.AIServerError("500")))
    bad = run(client, env["res"], "document", env["doc"].id, force=True).json()
    assert client.post(f"/ai/analyses/{bad['id']}/evaluation", headers=env["res"], json={"scores": scores}).status_code == 409  # 완료된 분석만 평가


def test_preflight_measures_tokens_with_free_counting_api_and_never_calls_generation(client, db_session, env, monkeypatch):
    p = ai_service.AnthropicProvider("sk-ant-test-0123456789abcdefghij", "fake-model-1")
    use(monkeypatch, p)
    calls = []

    def responder(method, url, **kw):
        calls.append(str(url))
        return httpx.Response(500, json={"error": {"message": "생성 호출이 일어나면 안 됨"}})

    patch_http(monkeypatch, responder)
    out = client.post("/ai/preflight", headers=env["adm"], json={"kind": "document", "target_id": str(env["doc"].id)}).json()
    assert out["input_tokens"] == 3000 and out["input_tokens_measured"] is True and "Token Counting" in out["input_tokens_note"]
    assert out["max_tokens"] == 12000 and out["max_cost_usd"] == pytest.approx(3000 * 2 / 1e6 + 12000 * 10 / 1e6) and out["expected_cost_usd"] < out["max_cost_usd"]
    assert out["recommended_approval_cap_usd"] >= out["max_cost_usd"] and out["request_top_level_keys"] == ["model", "max_tokens", "system", "messages"]
    assert {"temperature", "top_p", "top_k", "thinking"} <= set(out["not_sent"]) and out["connection"] == "unverified" and out["approval_required"] is True
    assert out["documents"][0]["content_hash"] and out["prompt_sha256"] and calls == []  # 생성 호출 없음(토큰 계산은 별도 무료 엔드포인트)
    assert client.post("/ai/preflight", headers=env["res"], json={"kind": "document", "target_id": str(env["doc"].id)}).status_code == 403  # 관리자 전용
    use(monkeypatch, None)
    nokey = client.post("/ai/preflight", headers=env["adm"], json={"kind": "document", "target_id": str(env["doc"].id)}).json()
    assert nokey["input_tokens_measured"] is False and "미측정" in nokey["input_tokens_note"] and nokey["connection"] == "not_configured"


def test_gate_uses_measured_tokens_and_max_output_cost_and_stops_before_paid_call(client, db_session, env, monkeypatch):
    p = ai_service.AnthropicProvider("sk-ant-test-0123456789abcdefghij", "fake-model-1")
    use(monkeypatch, p)
    sent = []
    count = {"v": 3000}

    def responder(method, url, **kw):
        sent.append(str(url))
        return httpx.Response(200, json={"content": [{"type": "text", "text": json.dumps(GOOD)}], "usage": {"input_tokens": 3000, "output_tokens": 500}, "stop_reason": "end_turn"})

    def fake(method, url, **kw):
        if str(url).endswith("/count_tokens"):
            if count["v"] is None:
                return httpx.Response(401, json={"error": {"message": "invalid x-api-key"}})
            return httpx.Response(200, json={"input_tokens": count["v"]})
        return responder(method, url, **kw)

    monkeypatch.setattr(httpx, "request", fake)
    cap = approve(client, env, max_cost_usd=0.2)  # 입력 추정 + 출력 12,000토큰 최대 비용(약 $0.13) 이내
    assert cap.status_code == 200, cap.text
    count["v"] = 100_000  # 실측 입력이 훨씬 크면 최대 비용(입력 $0.2 + 출력 $0.12)이 상한 $0.2를 넘는다
    r = run(client, env["res"], "document", env["doc"].id)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "budget_exceeded" and not any(u.endswith("/v1/messages") for u in sent)
    row = db_session.query(AICallApproval).one()
    assert row.used_at is None  # 차단됐으므로 승인은 소모되지 않는다
    count["v"] = None  # 무료 토큰 계산이 인증 오류 → 유료 호출 전에 중단
    r2 = run(client, env["res"], "document", env["doc"].id)
    assert r2.status_code == 502 and r2.json()["detail"]["code"] == "auth_error" and not any(u.endswith("/v1/messages") for u in sent)
    assert db_session.query(AICallApproval).one().used_at is None
    count["v"] = 3000  # 정상: 실측 3,000토큰 → 최대 비용 $0.126 ≤ $0.2 → 호출
    ok = run(client, env["res"], "document", env["doc"].id)
    assert ok.status_code == 200 and sum(u.endswith("/v1/messages") for u in sent) == 1
    assert db_session.query(AICallApproval).one().used_at is not None


def test_approval_cap_must_cover_max_output_cost(client, db_session, env, monkeypatch):
    use(monkeypatch, FakeProvider(GOOD))
    est = client.post("/ai/estimate", headers=env["res"], json={"kind": "document", "target_id": str(env["doc"].id)}).json()
    assert est["max_cost_usd"] > est["est_cost_usd"] and est["max_output_tokens"] == 12000
    low = approve(client, env, max_cost_usd=round(est["est_cost_usd"] + 0.0001, 4))  # 예상 비용만 덮는 상한은 최대 비용보다 작아 거부
    assert low.status_code == 422 and "최대 계산 비용" in low.text
    assert approve(client, env, max_cost_usd=round(est["max_cost_usd"] + 0.01, 3)).status_code == 200


def test_dotenv_file_values_are_used_when_environment_is_unset(tmp_path, monkeypatch):
    """서버가 apps/api/.env의 AI_PROVIDER·키를 실제로 읽는다(pydantic 설정과 별개로 os.environ에는 올라오지 않으므로 직접 읽는다)."""
    (tmp_path / ".env").write_text("AI_PROVIDER=anthropic\nANTHROPIC_API_KEY=sk-ant-dotenv-0123456789abcdef\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for k in ("AI_PROVIDER", "ANTHROPIC_API_KEY", "AI_MODEL"):
        monkeypatch.delenv(k, raising=False)
    assert ai_service.get_ai_provider() is None  # pytest 중에는 .env를 읽지 않는다(로컬 키가 테스트에 영향을 주지 않게)
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    p = ai_service.get_ai_provider()
    assert p is not None and p.name == "anthropic" and p.model == "claude-sonnet-5-5"
    assert "[REDACTED]" in ai_service.redact_secrets("key sk-ant-dotenv-0123456789abcdef")


