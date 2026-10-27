"""공급자 중립 AI 연동 서비스 — 분류·활용가치판정·구조화추출·3-6 분석이 공통으로 쓴다.

설계 원칙:
- 서버 측 환경변수로만 API 키를 읽는다(요청·DB에 키를 저장하지 않는다).
- AI_PROVIDER/AI_MODEL이 설정되지 않았거나 해당 공급자의 API 키 환경변수가 없으면
  get_ai_provider()가 None을 반환한다 — 호출부는 반드시 이 경우 규칙 기반으로 대체해야 하고,
  그 결과를 "AI 분석 완료"로 표시해서는 안 된다(ClassificationMethod.RULE_BASED로 저장).
- 모델 ID를 추측하지 않는다. Anthropic 기본값 claude-sonnet-5-5는 공식 모델 문서(platform.claude.com, 2026-10-27 확인)에 있는 ID이고,
  OpenAI는 공식 문서를 이 환경에서 대조하지 못해 기본 모델을 두지 않는다(AI_MODEL을 직접 지정해야 한다).
- 호출 실패는 예외를 삼키지 않고 AIServiceError(하위 종류별)로 올려서 호출부가 status="failed"와 정확한 사유를 남기게 한다.
  인증·권한·모델·한도·토큰 초과·시간 초과·5xx·잘못된 응답·응답 잘림을 구분하며 자동 재시도는 하지 않는다(재시도는 비용이 된다).
- 이 단계에서는 공개 원문(수집한 ICT 기사·정책문서)만 전송 대상으로 한다.
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

AI_PROVIDER_ENV = "AI_PROVIDER"  # "anthropic" | "openai" (| "mock": 개발·테스트 전용)
AI_MODEL_ENV = "AI_MODEL"
MAX_CHUNK_CHARS = 8000
REQUEST_TIMEOUT_SECONDS = 120.0
ANTHROPIC_VERSION = "2023-06-01"


def _getenv(name: str, default: str = "") -> str:
    """환경변수를 읽는다. 값이 없으면 apps/api/.env 파일(Git에 올라가지 않음)에서 읽는다 — 서버가 .env의 AI_* 설정을 쓰도록 하기 위함.
    자동 테스트(pytest) 중에는 .env를 읽지 않아 로컬 키 설정이 테스트에 영향을 주지 않는다."""
    v = os.environ.get(name)
    if v is not None:
        return v
    if "PYTEST_CURRENT_TEST" in os.environ:
        return default
    try:
        from dotenv import dotenv_values

        return str(dotenv_values(".env").get(name) or default)
    except Exception:  # noqa: BLE001 — .env가 없거나 읽을 수 없으면 기본값
        return default


_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")


def redact_secrets(text: str) -> str:
    """오류 메시지·로그·저장 문자열에서 API 키 값을 지운다(설정된 키 값과 'sk-...' 형태 모두)."""
    out = text or ""
    for env in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        v = _getenv(env).strip()
        if len(v) >= 8:
            out = out.replace(v, "[REDACTED]")
    return _KEY_PATTERN.sub("[REDACTED]", out)


class AIServiceError(Exception):
    """호출 실패. code는 화면·이력에 남기는 분류값이다."""

    code = "provider_error"
    user_message = "AI 호출에 실패했습니다"
    usage: tuple[int, int] | None = None  # (입력, 출력) 토큰 — 응답은 받았지만 쓸 수 없을 때(잘림 등) 비용 기록용
    raw_text: str | None = None  # 쓸 수 없던 응답 본문(사후 대조용) — 키는 포함되지 않는다

    def __init__(self, message: str | None = None, *, http_status: int | None = None):
        super().__init__(redact_secrets(message or self.user_message))
        self.http_status = http_status


class AIAuthError(AIServiceError):
    code, user_message = "auth_error", "API 키가 올바르지 않거나 권한이 없습니다(401/403) — 키와 조직 권한을 확인하세요"


class AIModelError(AIServiceError):
    code, user_message = "model_error", "모델 ID가 없거나 이 키로 사용할 수 없습니다 — AI_MODEL 설정을 확인하세요"


class AIRateLimitError(AIServiceError):
    code, user_message = "rate_limited", "제공자의 요청 한도를 초과했습니다(429) — 잠시 후 다시 시도하세요"


class AIContextError(AIServiceError):
    code, user_message = "context_too_large", "입력이 모델의 컨텍스트·토큰 제한을 넘었습니다 — 문서 수를 줄여 다시 요청하세요"


class AITimeoutError(AIServiceError):
    code, user_message = "timeout", "응답 시간이 초과되었습니다 — 제공자에게 요청이 전달되었다면 비용이 발생했을 수 있습니다"


class AIServerError(AIServiceError):
    code, user_message = "provider_5xx", "제공자 서버 오류입니다(5xx) — 잠시 후 다시 시도하세요"


class AIBadResponseError(AIServiceError):
    code, user_message = "bad_response", "응답 형식이 올바르지 않아 결과를 사용할 수 없습니다(JSON 오류)"


class AITruncatedError(AIServiceError):
    code, user_message = "truncated", "응답이 길이 제한으로 잘려 결과를 사용할 수 없습니다 — 입력을 줄이거나 출력 한도를 늘려야 합니다"


@dataclass
class AIResult:
    provider: str
    model: str
    text: str
    input_tokens: int = 0  # 공급자가 돌려준 실제 사용량(모의·미보고 시 0)
    output_tokens: int = 0
    stop_reason: str | None = None
    raw_text: str | None = None


class AIProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> AIResult: ...


def _raise_for_status(resp: httpx.Response, provider: str) -> None:
    """HTTP 상태를 종류별 예외로 바꾼다. 오류 본문은 앞부분만 쓴다."""
    if resp.status_code < 400:
        return
    try:
        body = resp.json()
        msg = (body.get("error", {}) or {}).get("message") if isinstance(body, dict) else None
    except ValueError:
        msg = None
    detail = f"{provider} {resp.status_code}: {(msg or resp.text or '')[:200]}"
    s = resp.status_code
    low = (msg or "").lower()
    if s in (401, 403):
        raise AIAuthError(detail, http_status=s)
    if s == 404:
        raise AIModelError(detail, http_status=s)
    if s == 429:
        raise AIRateLimitError(detail, http_status=s)
    if s == 413 or (s == 400 and any(k in low for k in ("too long", "context", "maximum", "max_tokens", "exceed"))):
        raise AIContextError(detail, http_status=s)
    if s == 400 and "model" in low:
        raise AIModelError(detail, http_status=s)
    if s >= 500:
        raise AIServerError(detail, http_status=s)
    raise AIServiceError(detail, http_status=s)


def _http(method: str, url: str, provider: str, **kwargs) -> httpx.Response:
    try:
        resp = httpx.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
    except httpx.TimeoutException as exc:
        raise AITimeoutError(f"{provider} 시간 초과: {exc.__class__.__name__}") from exc
    except httpx.HTTPError as exc:
        raise AIServiceError(f"{provider} 연결 실패: {exc.__class__.__name__}") from exc
    _raise_for_status(resp, provider)
    return resp


class AnthropicProvider:
    name = "anthropic"
    # 구조화 출력(output_config.format json_schema)은 공식 문서상 claude-sonnet-5-5 등에서 지원하지만 이 환경에서 실제 호출로 검증하지 못했으므로
    # 기본은 끄고(프롬프트 기반 JSON + 서버 스키마 검증), 첫 실호출 검증 후 AI_STRUCTURED_OUTPUT=1로 켠다.

    @property
    def supports_schema(self) -> bool:
        return _getenv("AI_STRUCTURED_OUTPUT").strip() == "1"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"}

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000, json_schema: dict | None = None) -> AIResult:
        # thinking 필드는 보내지 않는다 — Sonnet 5.5는 기본이 적응형 사고이며 "disabled"는 400 오류(공식 문서 확인). 사고 토큰은 출력 토큰으로 과금되고 max_tokens에 포함된다.
        body: dict = {"model": self.model, "max_tokens": max_tokens, "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]}
        if json_schema is not None and self.supports_schema:
            body["output_config"] = {"format": {"type": "json_schema", "schema": json_schema}}
        resp = _http("POST", "https://api.anthropic.com/v1/messages", self.name, headers=self._headers(), json=body)
        try:
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type", "text") == "text")
            usage = data.get("usage", {}) or {}
            stop = data.get("stop_reason")
        except (ValueError, AttributeError) as exc:
            raise AIBadResponseError("Anthropic 응답을 해석하지 못함") from exc
        used = (int(usage.get("input_tokens", 0) or 0), int(usage.get("output_tokens", 0) or 0))
        if stop == "max_tokens":  # 잘린 JSON은 파싱하지 않고 실패로 기록한다(토큰 사용량은 남긴다)
            err = AITruncatedError(f"Anthropic stop_reason=max_tokens (출력 {used[1]}토큰에서 잘림)")
            err.usage, err.raw_text = used, text
            raise err
        if stop == "refusal":
            err = AIBadResponseError("모델이 요청을 거절했습니다(stop_reason=refusal)")
            err.usage, err.raw_text = used, text
            raise err
        return AIResult(provider=self.name, model=self.model, text=text, stop_reason=stop, input_tokens=used[0], output_tokens=used[1], raw_text=text)

    def count_tokens(self, system_prompt: str, user_prompt: str) -> int:
        """공식 Token Counting API(POST /v1/messages/count_tokens, 무료·별도 요청 한도)로 실제 입력 토큰 수를 센다. 생성(유료) 호출이 아니다.
        공식 문서상 값은 추정치로 실제와 약간 다를 수 있다. thinking·temperature 등은 보내지 않는다(생성 호출과 같은 본문 형식)."""
        resp = _http("POST", "https://api.anthropic.com/v1/messages/count_tokens", self.name, headers=self._headers(),
                     json={"model": self.model, "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]})
        try:
            return int(resp.json()["input_tokens"])
        except (ValueError, KeyError, TypeError) as exc:
            raise AIBadResponseError("토큰 계산 응답을 해석하지 못함") from exc

    def list_models(self) -> list[str]:
        """키로 실제 사용 가능한 모델 ID 목록(진단용). 토큰을 쓰지 않는 조회 호출이다."""
        data = _http("GET", "https://api.anthropic.com/v1/models?limit=100", self.name, headers=self._headers()).json()
        return [m["id"] for m in data.get("data", []) if "id" in m]


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> AIResult:
        resp = _http("POST", "https://api.openai.com/v1/chat/completions", self.name, headers=self._headers(), json={
            "model": self.model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            "response_format": {"type": "json_object"}, "max_tokens": max_tokens,
        })
        try:
            data = resp.json()
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
            usage = data.get("usage", {}) or {}
            stop = choice.get("finish_reason")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIBadResponseError("OpenAI 응답을 해석하지 못함") from exc
        used = (int(usage.get("prompt_tokens", 0) or 0), int(usage.get("completion_tokens", 0) or 0))
        if stop == "length":
            err = AITruncatedError("OpenAI finish_reason=length (출력 한도에서 잘림)")
            err.usage, err.raw_text = used, text
            raise err
        return AIResult(provider=self.name, model=self.model, text=text, stop_reason=stop, input_tokens=used[0], output_tokens=used[1], raw_text=text)

    def list_models(self) -> list[str]:
        data = _http("GET", "https://api.openai.com/v1/models", self.name, headers=self._headers()).json()
        return sorted(m["id"] for m in data.get("data", []) if "id" in m)


# 공식 문서로 확인한 기본값만 둔다(추측 금지). OpenAI는 기본 모델 없음 → AI_MODEL 필수.
_DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5"}


def get_ai_provider() -> AIProvider | None:
    """서버 환경변수를 읽어 사용 가능한 AI 공급자를 돌려준다. 미설정이면 None(호출부는 규칙 기반으로 대체)."""
    provider_name = _getenv(AI_PROVIDER_ENV).strip().lower()
    if not provider_name:
        return None
    model = _getenv(AI_MODEL_ENV).strip() or _DEFAULT_MODELS.get(provider_name)
    if provider_name == "mock":
        # 개발·자동 테스트 전용 — 실제 AI가 아니다. AI_ALLOW_MOCK=1을 함께 지정해야만 켜지며 결과에 '모의 응답'이 표시된다.
        if _getenv("AI_ALLOW_MOCK").strip() != "1":
            return None
        from app.services.ai_mock import MockProvider

        return MockProvider()
    if not model:
        return None  # 모델 미지정(OpenAI 등) — 추측하지 않고 설정 필요로 처리
    if provider_name == "anthropic":
        key = _getenv("ANTHROPIC_API_KEY").strip()
        return AnthropicProvider(api_key=key, model=model) if key else None
    if provider_name == "openai":
        key = _getenv("OPENAI_API_KEY").strip()
        return OpenAIProvider(api_key=key, model=model) if key else None
    return None


def configuration_gaps() -> list[str]:
    """설정이 덜 된 이유를 키 값 없이 알려 준다(진단·화면 안내용)."""
    name = _getenv(AI_PROVIDER_ENV).strip().lower()
    if not name:
        return ["AI_PROVIDER가 설정되지 않음"]
    if name == "mock":
        return [] if _getenv("AI_ALLOW_MOCK").strip() == "1" else ["모의 공급자는 AI_ALLOW_MOCK=1이 필요함"]
    if name not in ("anthropic", "openai"):
        return [f"지원하지 않는 AI_PROVIDER: {name}"]
    gaps = []
    if not (_getenv(AI_MODEL_ENV).strip() or _DEFAULT_MODELS.get(name)):
        gaps.append("AI_MODEL이 필요함(이 공급자는 기본 모델을 두지 않음)")
    if not _getenv("ANTHROPIC_API_KEY" if name == "anthropic" else "OPENAI_API_KEY").strip():
        gaps.append("API 키 환경변수가 설정되지 않음")
    return gaps


def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """문단 경계를 최대한 지키면서 max_chars 이하로 분할한다."""
    if len(text) <= max_chars:
        return [text]
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > max_chars and current:
            chunks.append(current)
            current = para
        else:
            current = candidate
    if current:
        chunks.append(current)
    # 문단 하나가 max_chars보다 길면(예: 줄바꿈 없는 PDF 텍스트) 강제로 다시 자른다
    final_chunks: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            for i in range(0, len(chunk), max_chars):
                final_chunks.append(chunk[i : i + max_chars])
    return final_chunks or [""]


def extract_json_object(raw_text: str) -> dict:
    """AI 응답에서 JSON 객체를 최대한 관대하게 파싱한다(코드펜스 등을 감싸 주는 경우 대비)."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise AIBadResponseError(f"AI 응답에서 JSON 객체를 찾지 못함: {raw_text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIBadResponseError(f"AI 응답 JSON 파싱 실패: {exc}") from exc


# ---------------------------------------------------------------- 토큰·비용 추정 ----
def estimate_tokens(chars: int) -> int:
    """문자 수로 토큰을 거칠게 추정한다(한글·영문 혼합 기준 약 2.5자/토큰, 보수적으로 크게 잡음)."""
    return int(chars / 2.5) + 1


def cost_usd(price: tuple[float, float] | None, input_tokens: int, output_tokens: int) -> float | None:
    """단가(USD/100만 토큰: 입력, 출력)로 비용을 계산한다. 단가를 모르면 None — 0원으로 표시하지 않는다."""
    if price is None:
        return None
    return round(input_tokens * price[0] / 1_000_000 + output_tokens * price[1] / 1_000_000, 4)
