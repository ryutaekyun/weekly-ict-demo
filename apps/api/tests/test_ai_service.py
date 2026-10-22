import pytest

from app.services import ai_service


def test_get_ai_provider_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert ai_service.get_ai_provider() is None


def test_get_ai_provider_returns_none_when_provider_set_but_no_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert ai_service.get_ai_provider() is None


def test_get_ai_provider_returns_anthropic_when_configured(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    provider = ai_service.get_ai_provider()
    assert provider is not None
    assert provider.name == "anthropic"


def test_chunk_text_respects_max_chars_and_paragraph_boundaries():
    paragraphs = [f"Paragraph {i} " * 20 for i in range(10)]
    text = "\n\n".join(paragraphs)

    chunks = ai_service.chunk_text(text, max_chars=500)

    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    assert "".join(chunks).replace("\n\n", "") != ""  # 내용이 사라지지 않았는지 대략 확인


def test_chunk_text_single_chunk_when_short():
    text = "short text"
    assert ai_service.chunk_text(text, max_chars=500) == [text]


def test_extract_json_object_parses_plain_json():
    result = ai_service.extract_json_object('{"a": 1, "b": "x"}')
    assert result == {"a": 1, "b": "x"}


def test_extract_json_object_strips_code_fence():
    raw = '```json\n{"a": 1}\n```'
    assert ai_service.extract_json_object(raw) == {"a": 1}


def test_extract_json_object_raises_on_garbage():
    with pytest.raises(ai_service.AIServiceError):
        ai_service.extract_json_object("not json at all")
