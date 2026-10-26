"""
Трасса задачи ИИ: сколько занял каждый шаг модели и вся задача, что искали и что нашли.

- В result.trace задачи (видит только владелец): слова поиска, найденные контакты с именами,
  шаги модели с временем. Это ответ на «почему помощник так ответил».
- В лог ai-worker — одна строка на задачу. Его читает администратор сервера, а данные
  у каждого пользователя свои, поэтому имён там нет (только id контактов), номера и почта
  замаскированы, а слова поиска пишутся, только если AI_LOG_QUERIES=true.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..config import settings
from .llm import LLMProvider

logger = logging.getLogger("app.ai.jobs")

_DIGITS_EXCEPT_LAST = re.compile(r"\d(?=(?:\D*\d){2})")
_EMAIL_LOCAL = re.compile(r"[^@\s]+(?=@)")


class TimedLLM:
    """Обёртка над моделью: запоминает шаг (имя схемы) и время каждого вызова."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.name = inner.name
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        started = time.perf_counter()
        try:
            return await self._inner.complete_json(system, user, schema, schema_name)
        finally:
            self.calls.append({"step": schema_name, "ms": round((time.perf_counter() - started) * 1000)})


def mask(term: str) -> str:
    """Номер → только две последние цифры, email → без имени ящика."""
    return _DIGITS_EXCEPT_LAST.sub("•", _EMAIL_LOCAL.sub("•", term))


def log_job(job_id: str, kind: str, user_id: str, status: str, total_ms: int, trace: dict, error: str = "") -> None:
    llm = " ".join(f"{c['step']}={c['ms']}ms" for c in trace.get("llm", [])) or "-"
    found = trace.get("found") or trace.get("context") or []
    parts = [
        f"job={job_id}",
        f"kind={kind}",
        f"user={user_id[-6:]}",
        f"status={status}",
        f"total={total_ms}ms",
        f"llm=[{llm}]",
    ]
    if trace.get("intent") == "question":
        parts.append("intent=question")
    if settings.ai_log_queries:
        terms = [*trace.get("terms", []), *trace.get("search", [])]
        person = trace.get("person") or {}
        terms += [v for v in (person.get("first_name"), person.get("last_name")) if v]
        parts.append(f"search={[mask(t) for t in terms]}")
    if trace.get("source"):
        parts.append(f"source={trace['source']}")
    parts.append(f"found={len(found)}{[c['id'][-6:] for c in found]}")
    if error:
        parts.append(f"error={error!r}")
    logger.info("ai %s", " ".join(parts))
