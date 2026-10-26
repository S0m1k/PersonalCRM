"""
«Записать» распознаёт вопрос и предлагает «Спросить»; трасса задач ИИ (результат и лог воркера).
"""

from __future__ import annotations

import logging

import pytest

from app.ai.intent import looks_like_question
from app.ai.trace import mask
from app.config import settings

from .ai_fakes import FakeLLM, petya_responder
from .test_assistant_api import (  # noqa: F401 — фикстуры API помощника
    _capture,
    _contact,
    _job,
    _run,
    anna,
    assistant,
    client,
    system_db,
)

QUESTIONS = [
    "какой номер у ани",
    "8 (921) 553-53-33\n чей номер",
    "Кто живёт в Дубае?",
    "дай номер Пети",
    "а где работает Оля",
    "есть ли у Пети дети?",
    "Номер Ани?",
    "anna@mail.ru чья почта",
]
NOTES = [
    "встретил Петю, дочке 5 лет, переезжает в Дубай",
    "Петя сказал, что переезжает",
    "У Пети есть собака",
    "Спросил у Пети, как дела?",
    "созвонился с Олей из Сбера. Как дела у сына?",
    "Надо спросить у Пети, где он работает",
]


class TestIntent:
    @pytest.mark.parametrize("text", QUESTIONS)
    def test_questions(self, text):
        assert looks_like_question(text)

    @pytest.mark.parametrize("text", NOTES)
    def test_notes(self, text):
        assert not looks_like_question(text)


class TestCaptureSuggestsAsk:
    def test_question_is_not_sent_to_model(self, client, anna, assistant, system_db):
        llm = FakeLLM(petya_responder)
        job = _capture(client, anna, "какой номер у ани")

        assert _run(client, assistant, system_db, job["id"], llm=llm) == "done"
        result = _job(client, anna, job["id"]).json()["result"]

        assert result["suggest_ask"] is True
        assert result["actions"] == []
        assert llm.calls == []

    def test_force_records_anyway(self, client, anna, assistant, system_db):
        llm = FakeLLM(petya_responder)
        resp = client.post("/api/assistant/capture", json={"text": "Номер Пети?", "force": True}, headers=anna)

        assert _run(client, assistant, system_db, resp.json()["id"], llm=llm) == "done"
        assert _job(client, anna, resp.json()["id"]).json()["result"]["suggest_ask"] is False
        assert llm.calls


class TestTrace:
    def test_capture_trace_for_owner(self, client, anna, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", last_name="Смирнов")
        job = _capture(client, anna)

        _run(client, assistant, system_db, job["id"])
        trace = _job(client, anna, job["id"]).json()["result"]["trace"]

        assert trace["intent"] == "capture"
        assert trace["found"] == [{"id": petya["id"], "name": "Пётр Смирнов"}]
        assert [c["step"] for c in trace["llm"]] == ["person", "capture"]
        assert all(c["ms"] >= 0 for c in trace["llm"]) and trace["total_ms"] >= 0

    def test_ask_trace_shows_search_and_source(self, client, anna, assistant, system_db):
        anya = _contact(client, anna, first_name="Анюта", phones=[{"value": "8 (921) 553-53-33"}])

        def respond(schema_name, system, user):
            if schema_name == "search_terms":
                return {"names": ["Аня"], "keywords": []}
            return {"answer": "8 (921) 553-53-33", "contact_ids": [anya["id"]]}

        resp = client.post("/api/assistant/ask", json={"question": "какой номер у ани"}, headers=anna)
        _run(client, assistant, system_db, resp.json()["id"], llm=FakeLLM(respond))
        trace = _job(client, anna, resp.json()["id"]).json()["result"]["trace"]

        assert trace["terms"] == ["Аня"]
        assert trace["source"] == "search"
        assert trace["context"] == [{"id": anya["id"], "name": "Анюта"}]
        assert [c["step"] for c in trace["llm"]] == ["search_terms", "answer"]

    def test_worker_log_line_has_timing_and_ids_but_no_names(self, client, anna, assistant, system_db, caplog):
        anya = _contact(client, anna, first_name="Анюта", phones=[{"value": "8 (921) 553-53-33"}])

        def respond(schema_name, system, user):
            if schema_name == "search_terms":
                return {"names": [], "keywords": []}
            return {"answer": "Это номер Анюты", "contact_ids": [anya["id"]]}

        resp = client.post("/api/assistant/ask", json={"question": "89215535333 чей номер"}, headers=anna)
        with caplog.at_level(logging.INFO, logger="app.ai.jobs"):
            _run(client, assistant, system_db, resp.json()["id"], llm=FakeLLM(respond))

        line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("ai job="))
        assert "status=done" in line and "kind=ask" in line and "total=" in line
        assert "search_terms=" in line and "answer=" in line
        assert anya["id"][-6:] in line
        assert "Анюта" not in line
        assert "89215535333" not in line and "+79215535333" not in line
        assert "•33" in line

    def test_queries_can_be_kept_out_of_log(self, client, anna, assistant, system_db, caplog, monkeypatch):
        monkeypatch.setattr(settings, "ai_log_queries", False)
        job = _capture(client, anna)

        with caplog.at_level(logging.INFO, logger="app.ai.jobs"):
            _run(client, assistant, system_db, job["id"])

        line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("ai job="))
        assert "search=" not in line

    def test_failed_job_is_logged_with_error(self, client, anna, assistant, system_db, caplog):
        def broken(schema_name, system, user):
            raise RuntimeError("boom")

        job = _capture(client, anna)
        with caplog.at_level(logging.INFO, logger="app.ai.jobs"):
            assert _run(client, assistant, system_db, job["id"], llm=FakeLLM(broken)) == "failed"

        line = next(r.getMessage() for r in caplog.records if r.getMessage().startswith("ai job="))
        assert "status=failed" in line and "error=" in line


@pytest.mark.parametrize(
    ("raw", "masked"),
    [("+79215535333", "+•••••••••33"), ("anna.k@mail.ru", "•@mail.ru"), ("Аня", "Аня")],
)
def test_mask(raw, masked):
    assert mask(raw) == masked
