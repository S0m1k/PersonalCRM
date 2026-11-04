"""
Контекст чата (сводка старых сообщений + последние N) и выбор пути «запись / вопрос».
"""

from __future__ import annotations

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.ai.chat import build_history, route_message
from app.ai.llm import LLMError, LLMUnavailableError
from app.ai.tools import ToolError
from app.config import settings
from app.repositories import chats as chats_repo

from .ai_fakes import FailingLLM, FakeLLM


@pytest.fixture
def db():
    return AsyncMongoMockClient()["chat_ctx"]


async def _fill(db, n: int) -> tuple[str, str]:
    chat = await chats_repo.create_chat(db)
    last = None
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        last = await chats_repo.add_message(db, chat.id, role, f"сообщение {i}")
    return chat.id, last.id


def _summary_llm(text="Сводка старого."):
    return FakeLLM(lambda name, system, user: {"summary": text})


@pytest.fixture(autouse=True)
def _small_window(monkeypatch):
    monkeypatch.setattr(settings, "chat_context_messages", 4)
    monkeypatch.setattr(settings, "chat_summary_batch", 2)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Покажи, сколько у меня контактов по городам", "ask"),
        ("С кем я давно не общался?", "ask"),
        ("Динамика встреч по месяцам", "ask"),
        ("график по компаниям", "ask"),
        ("Распределение контактов по тегам", "ask"),
        ("Что я хотел спросить у Пети?", "ask"),
        ("встретил Петю, дочке 5 лет, переезжает в Дубай", "capture"),
        ("Созвонился с Мариной, узнал сколько ей лет", "capture"),
        ("Создай контакт Иван Петров, телефон 89215535333", "capture"),
        ("Удали контакт Иван Петров", "capture"),
        ("Петя переезжает в Дубай", "capture"),
    ],
)
def test_route_message(text, expected):
    assert route_message(text) == expected


async def test_short_history_goes_verbatim_without_summary(db):
    chat_id, last = await _fill(db, 4)  # 3 прежних + текущее
    llm = _summary_llm()

    history, trace = await build_history(db, llm, chat_id, last)

    assert "<сводка>" not in history and "сообщение 0" in history and "сообщение 3" not in history
    assert llm.calls == [] and trace["summarised"] is False and trace["in_context"] == 3


async def test_long_history_is_summarised_once_and_stored(db):
    chat_id, last = await _fill(db, 9)  # 8 прежних >= 4 + 2
    llm = _summary_llm("Говорили о Пете.")

    history, trace = await build_history(db, llm, chat_id, last)

    assert "<сводка>\nГоворили о Пете.\n</сводка>" in history
    assert "сообщение 3" not in history and "сообщение 4" in history and "сообщение 7" in history
    assert trace == {"messages_total": 8, "in_context": 4, "summary_upto": 4, "summarised": True}
    chat = await chats_repo.get_chat(db, chat_id)
    assert chat.summary == "Говорили о Пете." and chat.summary_upto == 4
    assert len(llm.calls) == 1 and "сообщение 0" in llm.calls[0]["user"] and "сообщение 4" not in llm.calls[0]["user"]

    # следующий вызов без новых сообщений модель не трогает: сводка уже сохранена
    again, _ = await build_history(db, llm, chat_id, last)
    assert len(llm.calls) == 1 and again == history


async def test_existing_summary_is_extended_with_aged_messages(db):
    chat_id, last = await _fill(db, 9)
    await build_history(db, _summary_llm("Первая."), chat_id, last)
    more = await chats_repo.add_message(db, chat_id, "user", "сообщение 9")
    for i in range(10, 13):
        more = await chats_repo.add_message(db, chat_id, "assistant", f"сообщение {i}")
    llm = _summary_llm("Первая и вторая.")

    history, trace = await build_history(db, llm, chat_id, more.id)

    assert "<сводка>\nПервая.\n</сводка>" in llm.calls[0]["user"]  # прежняя сводка уходит в модель
    assert trace["summary_upto"] == 8 and "Первая и вторая." in history


async def test_summary_failure_degrades_to_full_window_but_unavailability_propagates(db):
    chat_id, last = await _fill(db, 9)

    history, trace = await build_history(db, FailingLLM(LLMError("плохой JSON")), chat_id, last)
    assert trace["summarised"] is False and "сообщение 0" in history
    assert (await chats_repo.get_chat(db, chat_id)).summary == ""

    with pytest.raises(LLMUnavailableError):
        await build_history(db, FailingLLM(LLMUnavailableError("нет")), chat_id, last)


async def test_missing_chat_is_tool_error(db):
    with pytest.raises(ToolError):
        await build_history(db, _summary_llm(), "0" * 24, "0" * 24)


async def test_blocks_are_capped_and_validated(db):
    chat = await chats_repo.create_chat(db)
    points = [{"x": str(i), "y": i} for i in range(150)]
    rows = [{"a": i} for i in range(300)]

    msg = await chats_repo.add_message(db, chat.id, "assistant", "ок", [
        {"type": "chart", "chart": "bar", "series": [{"name": "s", "points": points}]},
        {"type": "table", "columns": [{"key": "a", "label": "A"}], "rows": rows},
    ])

    chart, table = msg.blocks
    assert len(chart.series[0].points) == 100 and len(table.rows) == 200
    with pytest.raises(ValueError):
        await chats_repo.add_message(db, chat.id, "assistant", "x", [{"type": "script", "html": "<b>"}])
    with pytest.raises(ValueError):
        await chats_repo.add_message(db, chat.id, "assistant", "x", [{"type": "chart", "chart": "radar"}])


def test_title_from_text():
    assert chats_repo.title_from_text("  много   пробелов \n тут ") == "много пробелов тут"
    assert chats_repo.title_from_text("") == "Новый чат"
    assert chats_repo.title_from_text("я" * 100).endswith("…")
