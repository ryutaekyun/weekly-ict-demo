"""공급자 중립 AI 연동 서비스 — 분류·활용가치판정·구조화추출이 공통으로 쓴다.

설계 원칙:
- 서버 측 환경변수로만 API 키를 읽는다(요청·DB에 키를 저장하지 않는다).
- AI_PROVIDER/AI_MODEL이 설정되지 않았거나 해당 공급자의 API 키 환경변수가 없으면
  get_ai_provider()가 None을 반환한다 — 호출부는 반드시 이 경우 규칙 기반으로 대체해야 하고,
  그 결과를 "AI 분석 완료"로 표시해서는 안 된다(ClassificationMethod.RULE_BASED로 저장).
- 긴 원문은 chunk_text()로 분할해 보낸다. 분할 결과를 병합하는 책임은 호출부(개별 분석 서비스)에 있다.
- 호출 실패는 예외를 삼키지 않고 AIServiceError로 올려서, 호출부가 AIAnalysisRun에
  status="failed"와 에러 메시지를 남기고 규칙 기반으로 폴백할 수 있게 한다.
- 이 단계에서는 공개 원문(수집한 ICT 기사·정책문서)만 전송 대상으로 한다 — 비공개 원고·내부
  문서를 사용자 확인 없이 외부 LLM에 보내는 호출부는 만들지 않는다.
"""

import json
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

AI_PROVIDER_ENV = "AI_PROVIDER"  # "anthropic" | "openai"
AI_MODEL_ENV = "AI_MODEL"
MAX_CHUNK_CHARS = 8000
REQUEST_TIMEOUT_SECONDS = 60.0


class AIServiceError(Exception):
    pass


@dataclass
class AIResult:
    provider: str
    model: str
    text: str
    input_tokens: int = 0  # 공급자가 돌려준 실제 사용량(모의·미보고 시 0)
    output_tokens: int = 0


class AIProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> AIResult: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> AIResult:
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            text = "".join(block.get("text", "") for block in data.get("content", []))
            usage = data.get("usage", {}) or {}
        except httpx.HTTPError as exc:
            raise AIServiceError(f"Anthropic API 호출 실패: {exc}") from exc
        return AIResult(provider=self.name, model=self.model, text=text,
                        input_tokens=int(usage.get("input_tokens", 0) or 0), output_tokens=int(usage.get("output_tokens", 0) or 0))


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def complete_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 2000) -> AIResult:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "max_tokens": max_tokens,
                },
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {}) or {}
        except (httpx.HTTPError, KeyError, IndexError) as exc:
            raise AIServiceError(f"OpenAI API 호출 실패: {exc}") from exc
        return AIResult(provider=self.name, model=self.model, text=text,
                        input_tokens=int(usage.get("prompt_tokens", 0) or 0), output_tokens=int(usage.get("completion_tokens", 0) or 0))


_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5-5",
    "openai": "gpt-4o-mini",
}


def get_ai_provider() -> AIProvider | None:
    """서버 환경변수를 읽어 사용 가능한 AI 공급자를 돌려준다. 미설정이면 None(호출부는 규칙 기반으로 대체)."""
    provider_name = os.environ.get(AI_PROVIDER_ENV, "").strip().lower()
    if not provider_name:
        return None
    model = os.environ.get(AI_MODEL_ENV, "").strip() or _DEFAULT_MODELS.get(provider_name)
    if provider_name == "mock":
        # 개발·자동 테스트 전용 — 실제 AI가 아니다. AI_ALLOW_MOCK=1을 함께 지정해야만 켜지며 결과에 '모의 응답'이 표시된다.
        if os.environ.get("AI_ALLOW_MOCK", "").strip() != "1":
            return None
        from app.services.ai_mock import MockProvider

        return MockProvider()
    if provider_name == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None
        return AnthropicProvider(api_key=key, model=model)
    if provider_name == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        return OpenAIProvider(api_key=key, model=model)
    return None


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
        raise AIServiceError(f"AI 응답에서 JSON 객체를 찾지 못함: {raw_text[:200]!r}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIServiceError(f"AI 응답 JSON 파싱 실패: {exc}") from exc


# 토큰 단가(USD/100만 토큰) — 공개 요금표가 바뀔 수 있으므로 '추정'으로만 쓰고 환경변수로 덮어쓸 수 있다.
_DEFAULT_PRICES = {"anthropic": (3.0, 15.0), "openai": (0.15, 0.6), "mock": (0.0, 0.0)}


def price_per_mtok(provider: str) -> tuple[float, float]:
    base = _DEFAULT_PRICES.get(provider, (3.0, 15.0))
    try:
        return (float(os.environ.get("AI_PRICE_IN_PER_MTOK", base[0])), float(os.environ.get("AI_PRICE_OUT_PER_MTOK", base[1])))
    except ValueError:
        return base


def estimate_tokens(chars: int) -> int:
    """문자 수로 토큰을 거칠게 추정한다(한글·영문 혼합 기준 약 2.5자/토큰, 보수적으로 크게 잡음)."""
    return int(chars / 2.5) + 1


def estimate_cost_usd(provider: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = price_per_mtok(provider)
    return round(input_tokens * pin / 1_000_000 + output_tokens * pout / 1_000_000, 4)
