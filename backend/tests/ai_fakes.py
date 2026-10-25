"""
Подделки для тестов ИИ: модель по сценарию, очередь без arq, хранилище на fakeredis.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from fakeredis import FakeAsyncRedis

from app.ai.jobs import Assistant, JobStore

Responder = Callable[[str, str, str], dict]


class FakeLLM:
    """Отвечает по имени схемы; запросы запоминает (проверяем, что ушло в модель)."""

    name = "fake"

    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        return self._responder(schema_name, system, user)


class FailingLLM:
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def complete_json(self, system: str, user: str, schema: dict, schema_name: str) -> dict:
        raise self._exc


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[str] = []

    async def enqueue(self, job_id: str) -> None:
        self.jobs.append(job_id)

    async def position(self, job_id: str) -> Optional[int]:
        return self.jobs.index(job_id) + 1 if job_id in self.jobs else None


def make_assistant() -> Assistant:
    return Assistant(store=JobStore(FakeAsyncRedis()), queue=FakeQueue())


def card_ids(user_message: str) -> list[str]:
    """id карточек из сообщения для модели (то, что «видит» модель)."""
    match = re.search(r"<карточки>\n(.*?)\n</карточки>", user_message, re.S)
    if not match or not match.group(1).startswith("["):
        return []
    try:
        return [c["id"] for c in json.loads(match.group(1))]
    except (ValueError, KeyError, TypeError):
        return []


def petya_responder(schema_name: str, system: str, user: str) -> dict:
    """Сценарий из DoD Sprint 6: «встретил Петю, дочке 5 лет, переезжает в Дубай»."""
    if schema_name == "person":
        return {"mention": "Петя", "first_name": "Пётр", "last_name": ""}
    if schema_name == "capture":
        ids = card_ids(user)
        return {
            "contact_id": ids[0] if ids else "",
            "fields": [{"key": "city", "value": "Дубай"}],
            "answers": [{"question_id": "", "question": "Сколько лет дочке?", "answer": "5 лет"}],
            "new_questions": [],
            "notes": ["Встретились, переезжает в Дубай"],
        }
    raise AssertionError(f"неожиданная схема {schema_name}")
