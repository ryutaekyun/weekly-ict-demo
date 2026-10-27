"""Phase 3-7 — 무료 시연 버전: 유료 외부 LLM 호출은 어떤 설정으로도 0건이어야 한다. 규칙 기반 기능과 모의 공급자 구분도 함께 검증한다."""

import json
from datetime import date

import httpx
import pytest

from app.models.ai_analysis import AIAnalysis, AICallApproval
from app.models.enums import FieldCode, UserRole
from app.services import ai_analysis_service as svc
from app.services import ai_service
from tests.conftest import auth_headers, make_user
from tests.test_phase35 import make_doc
from tests.test_ai_phase36 import FMVSS_A, run


@pytest.fixture
def all_paid_env(monkeypatch):
    """유료 AI 관련 환경변수·가짜 키를 전부 설정한 상태 — 그래도 외부 요청은 0건이어야 한다."""
    for k, v in {"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-ant-fake-0123456789abcdefghij", "OPENAI_API_KEY": "sk-proj-fake-0123456789abcdefghij",
                 "AI_MODEL": "claude-sonnet-5-5", "AI_ALLOW_PAID": "1", "AI_REQUIRE_APPROVAL": "0", "AI_STRUCTURED_OUTPUT": "1", "AI_ALLOW_MOCK": "0"}.items():
        monkeypatch.setenv(k, v)
    calls = []
    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: calls.append(str(url)) or httpx.Response(200, json={}))
    return calls


def test_code_level_lock_is_on_and_not_reachable_by_environment(all_paid_env):
    assert ai_service.PAID_AI_DISABLED is True
    assert ai_service.get_ai_provider() is None  # 키·AI_ALLOW_PAID·모델을 모두 지정해도 공급자가 만들어지지 않는다
    assert any("코드 수준" in g for g in ai_service.configuration_gaps())
    for openai in (False, True):
        monkey_provider = (ai_service.OpenAIProvider if openai else ai_service.AnthropicProvider)("sk-fake-0123456789abcdef", "m")
        with pytest.raises(ai_service.AIBlockedError):  # 공급자 객체를 직접 만들어도 HTTP 계층에서 차단
            monkey_provider.complete_json("s", "u")
    with pytest.raises(ai_service.AIBlockedError):
        ai_service.AnthropicProvider("sk-fake-0123456789abcdef", "m").count_tokens("s", "u")
    with pytest.raises(ai_service.AIBlockedError):
        ai_service.AnthropicProvider("sk-fake-0123456789abcdef", "m").list_models()
    assert all_paid_env == []  # 외부 AI 요청 0건


def test_no_external_llm_request_through_any_api_path_even_with_keys(client, db_session, all_paid_env):
    make_user(db_session, "fz-res@example.com", UserRole.RESEARCHER)
    make_user(db_session, "fz-adm@example.com", UserRole.ADMIN)
    res, adm = auth_headers(client, "fz-res@example.com"), auth_headers(client, "fz-adm@example.com")
    doc = make_doc(db_session, title="FMVSS", field=FieldCode.AI, full_text=FMVSS_A)
    st = client.get("/ai/status", headers=res).json()
    assert st["configured"] is False and st["paid_locked"] is True and "유료 AI를 사용하지 않습니다" in st["message"]
    r = run(client, res, "document", doc.id)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ai_not_configured"
    body = {"kind": "document", "target_id": str(doc.id)}
    assert client.post("/ai/diagnostics", headers=adm).json()["connection"] == "blocked"  # 관리자 화면에서도 연결 진단 불가
    assert client.post("/ai/approvals", headers=adm, json={**body, "max_cost_usd": 0.5}).status_code == 403
    assert client.post("/ai/preflight", headers=adm, json=body).status_code == 403
    assert client.put("/ai/pricing", headers=adm, json={"provider": "anthropic", "model": "claude-sonnet-5-5", "input_per_mtok": 2, "output_per_mtok": 10, "effective_date": str(date.today())}).status_code == 403
    assert db_session.query(AIAnalysis).count() == 0 and db_session.query(AICallApproval).count() == 0
    assert all_paid_env == []


def test_general_http_collection_is_not_blocked_but_ai_endpoints_are(monkeypatch):
    """공식 원문 수집 같은 일반 HTTP는 계속 허용하고 AI 서비스 엔드포인트만 차단한다."""
    seen = []
    monkeypatch.setattr(httpx, "request", lambda method, url, **kw: seen.append(str(url)) or httpx.Response(200, json={"ok": True}))
    assert ai_service._http("GET", "https://www.federalregister.gov/api/v1/documents.json", "collector").json() == {"ok": True}
    with pytest.raises(ai_service.AIBlockedError):
        ai_service._http("POST", "https://api.openai.com/v1/chat/completions", "openai")
    assert seen == ["https://www.federalregister.gov/api/v1/documents.json"]


def test_no_automatic_provider_fallback_to_another_paid_provider(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "bad")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-proj-fake-0123456789abcdefghij")
    monkeypatch.setenv("AI_ALLOW_MOCK", "0")
    assert ai_service.get_ai_provider() is None  # 한 공급자가 막혀도 다른 유료 공급자로 넘어가지 않는다


def test_mock_provider_requires_explicit_test_setting_and_results_are_never_verified(client, db_session, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.delenv("AI_ALLOW_MOCK", raising=False)
    assert ai_service.get_ai_provider() is None  # D: 명시적 테스트 설정이 없으면 모의 공급자는 실행 불가
    monkeypatch.setenv("AI_ALLOW_MOCK", "1")
    monkeypatch.setenv("AI_REQUIRE_APPROVAL", "0")
    make_user(db_session, "fz-m@example.com", UserRole.RESEARCHER)
    make_user(db_session, "fz-ap@example.com", UserRole.APPROVER)
    h = auth_headers(client, "fz-m@example.com")
    doc = make_doc(db_session, title="FMVSS", field=FieldCode.AI, full_text=FMVSS_A)
    out = run(client, h, "document", doc.id).json()
    assert out["is_mock"] is True and out["provider"] == "mock" and "실제 AI 분석이 아닙니다" in out["notice"]
    assert out["verification_status"] != "researcher_verified"  # E: 모의 결과는 검증 완료로 표시되지 않는다
    assert client.post(f"/ai/analyses/{out['id']}/public-approval", headers=auth_headers(client, "fz-ap@example.com")).status_code == 409  # 공개 불가
    from app import export_public_snapshot as snap

    s = json.dumps(snap.build_snapshot(db_session), ensure_ascii=False)
    assert "ai_results" not in s and "mock" not in s.lower()
