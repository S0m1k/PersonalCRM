"""
Провайдеры моделей: формат запроса, разбор ответа, ошибки и запасной провайдер.
HTTP подменён httpx.MockTransport — в сеть тесты не ходят.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.ai.llm import (
    ClaudeProvider,
    FallbackProvider,
    LLMError,
    LLMUnavailableError,
    OpenAICompatibleProvider,
    _parse_json,
    build_provider,
)
from app.config import Settings

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}


def _openai(handler, **kwargs) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "http://ollama:11434/v1/", "qwen3.5:4b", transport=httpx.MockTransport(handler), **kwargs
    )


def _completion(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


async def test_openai_request_uses_json_schema_and_reasoning_effort():
    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["url"] = str(request.url)
        sent["body"] = json.loads(request.content)
        sent["auth"] = request.headers.get("authorization")
        return _completion('{"a": "б"}')

    result = await _openai(handler, reasoning_effort="none").complete_json("sys", "текст", SCHEMA, "thing")

    assert result == {"a": "б"}
    assert sent["url"] == "http://ollama:11434/v1/chat/completions"
    assert sent["body"]["response_format"]["json_schema"] == {"name": "thing", "strict": True, "schema": SCHEMA}
    assert sent["body"]["reasoning_effort"] == "none"
    assert sent["body"]["temperature"] == 0
    assert sent["body"]["messages"][1] == {"role": "user", "content": "текст"}
    assert sent["auth"] is None


async def test_openai_sends_api_key_and_omits_empty_reasoning():
    sent = {}

    def handler(request):
        sent["auth"] = request.headers.get("authorization")
        sent["body"] = json.loads(request.content)
        return _completion('{"a": "x"}')

    await _openai(handler, api_key="k").complete_json("s", "u", SCHEMA, "t")

    assert sent["auth"] == "Bearer k"
    assert "reasoning_effort" not in sent["body"]


@pytest.mark.parametrize(
    "text",
    ['{"a": "x"}', '```json\n{"a": "x"}\n```', 'Вот ответ: {"a": "x"} — готово'],
)
def test_parse_json_tolerates_wrapping(text):
    assert _parse_json(text) == {"a": "x"}


@pytest.mark.parametrize("text", ["", "нет json", "[1, 2]", '{"a": '])
def test_parse_json_rejects_garbage(text):
    with pytest.raises(LLMError):
        _parse_json(text)


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(500), LLMUnavailableError),
        (httpx.Response(503), LLMUnavailableError),
        (httpx.Response(429), LLMUnavailableError),
        (httpx.Response(400, json={"error": "bad"}), LLMError),
        (httpx.Response(200, text="not json"), LLMError),
        (httpx.Response(200, json={"choices": []}), LLMError),
    ],
)
async def test_openai_errors(response, error):
    provider = _openai(lambda request: response)

    with pytest.raises(error) as info:
        await provider.complete_json("s", "u", SCHEMA, "t")

    if error is LLMError:
        assert not isinstance(info.value, LLMUnavailableError)


async def test_connection_error_is_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailableError):
        await _openai(handler).complete_json("s", "u", SCHEMA, "t")


async def test_claude_forces_tool_and_reads_its_input():
    sent = {}

    def handler(request):
        sent["body"] = json.loads(request.content)
        sent["headers"] = request.headers
        return httpx.Response(200, json={"content": [{"type": "tool_use", "name": "t", "input": {"a": "x"}}]})

    provider = ClaudeProvider("key", "claude-haiku-5-5", transport=httpx.MockTransport(handler))
    result = await provider.complete_json("sys", "u", SCHEMA, "t")

    assert result == {"a": "x"}
    assert sent["body"]["tool_choice"] == {"type": "tool", "name": "t"}
    assert sent["body"]["tools"][0]["input_schema"] == SCHEMA
    assert sent["body"]["system"] == "sys"
    assert sent["headers"]["x-api-key"] == "key"


class _Stub:
    def __init__(self, name, result=None, exc=None):
        self.name, self._result, self._exc, self.called = name, result, exc, False

    async def complete_json(self, *args):
        self.called = True
        if self._exc:
            raise self._exc
        return self._result


async def test_fallback_only_when_primary_unavailable():
    backup = _Stub("backup", {"a": "backup"})

    down = FallbackProvider(_Stub("p", exc=LLMUnavailableError("down")), backup)
    assert await down.complete_json("s", "u", SCHEMA, "t") == {"a": "backup"}

    backup.called = False
    broken = FallbackProvider(_Stub("p", exc=LLMError("bad json")), backup)
    with pytest.raises(LLMError):
        await broken.complete_json("s", "u", SCHEMA, "t")
    assert backup.called is False


def test_fallback_is_off_by_default():
    assert isinstance(build_provider(Settings(llm_fallback="")), OpenAICompatibleProvider)
    # Без ключа запасной провайдер не включается
    assert isinstance(build_provider(Settings(llm_fallback="claude", anthropic_api_key=None)), OpenAICompatibleProvider)
    assert isinstance(build_provider(Settings(llm_fallback="claude", anthropic_api_key="k")), FallbackProvider)
