"""
Провайдеры языковых моделей.

LLMProvider.complete_json — один запрос «системный промпт + текст → JSON по схеме».
Ответ модели — недоверенные данные: вызывающий код проверяет его сам.

- OpenAICompatibleProvider — /chat/completions с response_format=json_schema
  (Ollama, vLLM, llama.cpp server, LM Studio). По умолчанию — локальный Qwen в Ollama.
- ClaudeProvider — Anthropic Messages API, JSON через принудительный вызов инструмента.
  Выключен по умолчанию (LLM_FALLBACK=claude + ANTHROPIC_API_KEY).
- FallbackProvider — запасной провайдер, только если основной недоступен
  (сеть, таймаут, 5xx), а не на каждую ошибку разбора.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Protocol

import httpx

from ..config import Settings, settings

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_OUTPUT_TOKENS = 1500


class LLMError(Exception):
    """Модель ответила, но не тем (не JSON, пустой ответ, 4xx)."""


class LLMUnavailableError(LLMError):
    """Модель недоступна: сеть, таймаут, 5xx. Задачу имеет смысл повторить."""


class LLMProvider(Protocol):
    name: str

    async def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> dict:
        ...


def _parse_json(text: str) -> dict:
    """JSON-объект из ответа; модели иногда оборачивают его в ```json … ```."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{"):] if "{" in cleaned else cleaned
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end < start:
        raise LLMError("Модель вернула не JSON")
    try:
        value = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Модель вернула некорректный JSON: {exc}") from None
    if not isinstance(value, dict):
        raise LLMError("Модель вернула не объект")
    return value


async def _post(client: httpx.AsyncClient, url: str, **kwargs: Any) -> dict:
    try:
        resp = await client.post(url, **kwargs)
    except httpx.TimeoutException as exc:
        raise LLMUnavailableError(f"Модель не ответила вовремя ({url})") from exc
    except httpx.HTTPError as exc:
        raise LLMUnavailableError(f"Модель недоступна ({url}): {exc}") from exc
    if resp.status_code >= 500 or resp.status_code == 429:
        raise LLMUnavailableError(f"Модель вернула {resp.status_code}")
    if resp.status_code >= 400:
        # Тело ответа не логируем целиком: там может быть эхо запроса с данными пользователя
        raise LLMError(f"Модель отклонила запрос: HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        raise LLMError("Ответ модели — не JSON") from None


class OpenAICompatibleProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: Optional[str] = None,
        timeout_s: float = 180,
        reasoning_effort: str = "",
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.name = f"openai:{model}"
        self.model = model
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout_s
        self._reasoning_effort = reasoning_effort
        self._transport = transport

    async def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            data = await _post(client, self._url, json=body, headers=self._headers)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise LLMError("Неожиданный формат ответа модели") from None
        return _parse_json(content)


class ClaudeProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_s: float = 60,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.name = f"claude:{model}"
        self.model = model
        self._headers = {"x-api-key": api_key, "anthropic-version": ANTHROPIC_VERSION}
        self._timeout = timeout_s
        self._transport = transport

    async def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> dict:
        body = {
            "model": self.model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [{"name": schema_name, "description": "Структурированный ответ", "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": schema_name},
        }
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            data = await _post(client, ANTHROPIC_URL, json=body, headers=self._headers)
        for block in data.get("content") or []:
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                return block["input"]
        raise LLMError("Claude не вернул структурированный ответ")


class FallbackProvider:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.name = f"{primary.name} (запасной: {fallback.name})"
        self._primary = primary
        self._fallback = fallback

    async def complete_json(self, system: str, user: str, schema: dict[str, Any], schema_name: str) -> dict:
        try:
            return await self._primary.complete_json(system, user, schema, schema_name)
        except LLMUnavailableError as exc:
            logger.warning("Основная модель недоступна (%s), запрос идёт в %s", exc, self._fallback.name)
            return await self._fallback.complete_json(system, user, schema, schema_name)


def build_provider(s: Settings = settings) -> LLMProvider:
    primary = OpenAICompatibleProvider(
        base_url=s.llm_base_url,
        model=s.llm_model,
        api_key=s.llm_api_key,
        timeout_s=s.llm_timeout_s,
        reasoning_effort=s.llm_reasoning_effort,
    )
    if s.llm_fallback == "claude":
        if not s.anthropic_api_key:
            logger.warning("LLM_FALLBACK=claude, но ANTHROPIC_API_KEY не задан — запасной провайдер выключен")
            return primary
        return FallbackProvider(primary, ClaudeProvider(s.anthropic_api_key, s.anthropic_model))
    return primary
