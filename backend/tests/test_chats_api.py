"""
Чаты помощника через API: список, переименование, удаление, история, отправка сообщения
и ответ воркера (аналитика с графиками, предпросмотр записи, досье). Модель — по сценарию.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

import pytest
from arq import Retry
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.ai.jobs import get_assistant
from app.ai.worker import process_job
from app.config import settings
from app.db import get_db
from app.main import app

from .ai_fakes import FailingLLM, FakeLLM, make_assistant, petya_responder
from app.ai.llm import LLMUnavailableError

BASE = "/api/assistant"


@pytest.fixture
def system_db():
    return AsyncMongoMockClient()["test_chats"]


@pytest.fixture
def assistant():
    return make_assistant()


@pytest.fixture
def client(system_db, assistant):
    app.dependency_overrides[get_db] = lambda: system_db
    app.dependency_overrides[get_assistant] = lambda: assistant
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email: str) -> dict:
    resp = client.post("/api/auth/register", json={"email": email, "password": "password-123"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def anna(client):
    return _register(client, "anna@example.com")


@pytest.fixture
def boris(client):
    return _register(client, "boris@example.com")


def _chat(client, auth, title=None) -> dict:
    resp = client.post(f"{BASE}/chats", json={"title": title}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _send(client, auth, chat_id, text) -> dict:
    resp = client.post(f"{BASE}/chats/{chat_id}/messages", json={"text": text}, headers=auth)
    assert resp.status_code == 202, resp.text
    return resp.json()


def _contact(client, auth, **body) -> dict:
    resp = client.post("/api/contacts/", json=body, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _run(client, assistant, system_db, job_id, llm) -> str:
    return client.portal.call(lambda: process_job(assistant.store, system_db, llm, job_id))


def _history(client, auth, chat_id, **params) -> dict:
    resp = client.get(f"{BASE}/chats/{chat_id}/messages", params=params, headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def chat_responder(plan=None, explain="Больше всего контактов в Москве."):
    """Сценарий модели для чата; plan — список вызовов инструментов (поля, не указанные — пустые)."""
    blank = {"field": "", "chart": "", "period": "", "from": "", "to": "", "contact_id": "", "days": 0, "limit": 0}

    def respond(schema_name, system, user):
        if schema_name == "plan":
            return {"calls": [{**blank, **c} for c in (plan or [])]}
        if schema_name == "explain":
            return {"text": explain}
        if schema_name == "summary":
            return {"summary": "Обсуждали города контактов."}
        if schema_name == "search_terms":
            return {"names": ["Пётр"], "keywords": []}
        if schema_name == "answer":
            ids = re.findall(r'"id": "([0-9a-f]{24})"', user)
            return {"answer": "Пётр живёт в Москве.", "contact_ids": ids[:1]}
        return petya_responder(schema_name, system, user)

    return respond


# --- CRUD ------------------------------------------------------------------------------------


def test_create_list_rename_and_delete_chat(client, anna):
    first = _chat(client, anna, "Первый")
    second = _chat(client, anna)

    assert second["title"] == "Новый чат" and first["archived"] is False
    listed = client.get(f"{BASE}/chats", headers=anna).json()
    assert [c["id"] for c in listed] == [second["id"], first["id"]]  # новые сверху

    renamed = client.patch(f"{BASE}/chats/{first['id']}", json={"title": "  Города  "}, headers=anna)
    assert renamed.status_code == 200 and renamed.json()["title"] == "Города"
    assert [c["id"] for c in client.get(f"{BASE}/chats", headers=anna).json()] == [first["id"], second["id"]]

    found = client.get(f"{BASE}/chats", params={"q": "горо"}, headers=anna).json()
    assert [c["id"] for c in found] == [first["id"]]

    assert client.delete(f"{BASE}/chats/{second['id']}", headers=anna).status_code == 204
    assert client.delete(f"{BASE}/chats/{second['id']}", headers=anna).status_code == 404
    assert len(client.get(f"{BASE}/chats", headers=anna).json()) == 1


def test_archive_hides_chat_from_default_list(client, anna):
    chat = _chat(client, anna, "Старый")

    client.patch(f"{BASE}/chats/{chat['id']}", json={"archived": True}, headers=anna)

    assert client.get(f"{BASE}/chats", headers=anna).json() == []
    assert len(client.get(f"{BASE}/chats", params={"archived": True}, headers=anna).json()) == 1


def test_update_validation_and_unknown_ids(client, anna):
    chat = _chat(client, anna)

    assert client.patch(f"{BASE}/chats/{chat['id']}", json={"title": ""}, headers=anna).status_code == 422
    assert client.patch(f"{BASE}/chats/{chat['id']}", json={}, headers=anna).json()["id"] == chat["id"]
    assert client.patch(f"{BASE}/chats/{'0' * 24}", json={"title": "x"}, headers=anna).status_code == 404
    assert client.patch(f"{BASE}/chats/плохой", json={"title": "x"}, headers=anna).status_code == 404
    assert client.get(f"{BASE}/chats/{'0' * 24}/messages", headers=anna).status_code == 404


def test_chat_count_is_capped(client, anna, monkeypatch):
    monkeypatch.setattr(settings, "chat_max_per_user", 2)
    _chat(client, anna)
    _chat(client, anna)

    assert client.post(f"{BASE}/chats", json={}, headers=anna).status_code == 409


def test_requires_login(client):
    assert client.get(f"{BASE}/chats").status_code == 401


def test_chats_of_one_user_are_invisible_to_another(client, anna, boris):
    chat = _chat(client, anna, "Секрет Анны")
    _send(client, anna, chat["id"], "Сколько у меня контактов по городам?")

    assert client.get(f"{BASE}/chats", headers=boris).json() == []
    assert client.get(f"{BASE}/chats/{chat['id']}/messages", headers=boris).status_code == 404
    assert client.post(f"{BASE}/chats/{chat['id']}/messages", json={"text": "привет"}, headers=boris).status_code == 404
    assert client.patch(f"{BASE}/chats/{chat['id']}", json={"title": "x"}, headers=boris).status_code == 404
    assert client.delete(f"{BASE}/chats/{chat['id']}", headers=boris).status_code == 404
    assert len(_history(client, anna, chat["id"])["items"]) == 1  # у Анны всё на месте


# --- отправка сообщения ----------------------------------------------------------------------


def test_send_message_stores_it_enqueues_job_and_titles_chat(client, anna, assistant):
    chat = _chat(client, anna)

    sent = _send(client, anna, chat["id"], "  Сколько у меня контактов по городам?  ")

    assert sent["role"] == "user" and sent["content"] == "Сколько у меня контактов по городам?"
    assert sent["job"]["kind"] == "chat" and sent["job"]["status"] == "queued"
    assert assistant.queue.jobs == [sent["job"]["id"]]
    record = client.portal.call(lambda: assistant.store.get(sent["job"]["id"]))
    assert record["input"] == {"chat_id": chat["id"], "message_id": sent["id"]}
    assert client.get(f"{BASE}/chats", headers=anna).json()[0]["title"] == "Сколько у меня контактов по городам?"


def test_title_is_truncated_on_word_boundary_and_not_overwritten(client, anna):
    chat = _chat(client, anna)
    long_text = "Покажи подробную динамику моих встреч с коллегами и друзьями по месяцам за последний год"

    _send(client, anna, chat["id"], long_text)
    _send(client, anna, chat["id"], "Второе сообщение")

    title = client.get(f"{BASE}/chats", headers=anna).json()[0]["title"]
    assert title.endswith("…") and len(title) <= 61 and long_text.startswith(title[:-1])
    renamed = _chat(client, anna, "Моё название")
    _send(client, anna, renamed["id"], "что-нибудь")
    assert client.get(f"{BASE}/chats", headers=anna).json()[0]["title"] == "Моё название"


def test_message_limits(client, anna, monkeypatch):
    chat = _chat(client, anna)

    too_long = client.post(f"{BASE}/chats/{chat['id']}/messages", json={"text": "я" * 4001}, headers=anna)
    empty = client.post(f"{BASE}/chats/{chat['id']}/messages", json={"text": "   "}, headers=anna)
    assert too_long.status_code == 422 and empty.status_code == 422
    assert client.post(f"{BASE}/chats/{chat['id']}/messages", json={"text": "я" * 4000}, headers=anna).status_code == 202

    monkeypatch.setattr(settings, "chat_max_messages", 1)
    assert client.post(f"{BASE}/chats/{chat['id']}/messages", json={"text": "ещё"}, headers=anna).status_code == 409


def test_queue_limit_returns_429_and_drops_the_message(client, anna, monkeypatch):
    monkeypatch.setattr(settings, "ai_user_max_queued", 1)
    chat = _chat(client, anna)
    _send(client, anna, chat["id"], "первое")

    resp = client.post(f"{BASE}/chats/{chat['id']}/messages", json={"text": "второе"}, headers=anna)

    assert resp.status_code == 429
    assert [m["content"] for m in _history(client, anna, chat["id"])["items"]] == ["первое"]


def test_history_pagination(client, anna, monkeypatch):
    monkeypatch.setattr(settings, "ai_user_max_queued", 100)
    chat = _chat(client, anna)
    for i in range(5):
        _send(client, anna, chat["id"], f"сообщение {i}")

    page = _history(client, anna, chat["id"], limit=2)
    assert [m["content"] for m in page["items"]] == ["сообщение 3", "сообщение 4"] and page["has_more"]
    older = _history(client, anna, chat["id"], limit=2, before=page["items"][0]["id"])
    assert [m["content"] for m in older["items"]] == ["сообщение 1", "сообщение 2"] and older["has_more"]
    oldest = _history(client, anna, chat["id"], limit=2, before=older["items"][0]["id"])
    assert [m["content"] for m in oldest["items"]] == ["сообщение 0"] and not oldest["has_more"]


def test_delete_chat_removes_its_messages(client, anna, system_db):
    chat = _chat(client, anna)
    _send(client, anna, chat["id"], "привет")

    client.delete(f"{BASE}/chats/{chat['id']}", headers=anna)

    left = client.portal.call(lambda: system_db.list_collection_names())
    for name in left:
        assert client.portal.call(lambda n=name: system_db[n].count_documents({"chat_id": chat["id"]})) == 0


# --- ответ воркера ---------------------------------------------------------------------------


def test_analytics_question_returns_chart_with_real_numbers(client, anna, assistant, system_db):
    for name, city in (("А", "Москва"), ("Б", "Москва"), ("В", "Дубай")):
        _contact(client, anna, first_name=name, city=city)
    chat = _chat(client, anna)
    sent = _send(client, anna, chat["id"], "Покажи, сколько у меня контактов по городам")
    # модель пытается «подправить» цифры в тексте — на график это не влияет
    llm = FakeLLM(chat_responder([{"tool": "count_contacts_by", "field": "city", "chart": "pie"}], "В Москве 999 контактов."))

    assert _run(client, assistant, system_db, sent["job"]["id"], llm) == "done"

    job = client.get(f"{BASE}/jobs/{sent['job']['id']}", headers=anna).json()
    assert job["status"] == "done" and job["result"]["message_id"]
    reply = _history(client, anna, chat["id"])["items"][-1]
    assert reply["role"] == "assistant" and reply["job_id"] == sent["job"]["id"]
    text, chart = reply["blocks"]
    assert text == {"type": "text", "text": "В Москве 999 контактов."} and reply["content"] == text["text"]
    assert chart["type"] == "chart" and chart["chart"] == "pie"
    assert chart["series"][0]["points"] == [{"x": "Москва", "y": 2.0}, {"x": "Дубай", "y": 1.0}]
    explain = next(c for c in llm.calls if c["schema_name"] == "explain")
    assert '"count": 2' in explain["user"] and "<данные>" in explain["user"]
    assert job["result"]["trace"]["tools"] == [{"tool": "count_contacts_by", "params": {"field": "city", "chart": "pie"}}]


def test_second_message_sees_conversation_history(client, anna, assistant, system_db):
    _contact(client, anna, first_name="Пётр", city="Москва")
    chat = _chat(client, anna)
    first = _send(client, anna, chat["id"], "Покажи, сколько у меня контактов по городам")
    _run(client, assistant, system_db, first["job"]["id"], FakeLLM(chat_responder([{"tool": "count_contacts_by", "field": "city"}])))
    second = _send(client, anna, chat["id"], "А где живёт Пётр?")
    llm = FakeLLM(chat_responder([]))

    _run(client, assistant, system_db, second["job"]["id"], llm)

    plan_call = next(c for c in llm.calls if c["schema_name"] == "plan")
    assert "<сообщения>" in plan_call["user"] and "Пользователь: Покажи, сколько у меня контактов" in plan_call["user"]
    assert "[график «Контакты по городу»]" in plan_call["user"] or "[график" in plan_call["user"]
    answer_call = next(c for c in llm.calls if c["schema_name"] == "answer")
    assert "<история>" in answer_call["user"] and "Помощник:" in answer_call["user"]
    reply = _history(client, anna, chat["id"])["items"][-1]
    assert reply["blocks"][0]["text"] == "Пётр живёт в Москве."
    assert reply["blocks"][1]["type"] == "contacts" and reply["blocks"][1]["contacts"][0]["name"] == "Пётр"


@pytest.mark.parametrize(
    "plan",
    [
        [{"tool": "drop_database"}],
        [{"tool": "count_contacts_by", "field": "password_hash"}],
        [{"tool": "stale_contacts", "days": 999999}],
    ],
)
def test_bad_model_plan_falls_back_to_plain_answer(client, anna, assistant, system_db, plan):
    _contact(client, anna, first_name="Пётр", city="Москва")
    chat = _chat(client, anna)
    sent = _send(client, anna, chat["id"], "Где живёт Пётр?")

    status = _run(client, assistant, system_db, sent["job"]["id"], FakeLLM(chat_responder(plan)))

    assert status == "done"
    reply = _history(client, anna, chat["id"])["items"][-1]
    assert reply["blocks"][0]["text"] == "Пётр живёт в Москве."


def test_plan_is_capped_at_three_known_calls():
    from app.ai.chat import plan_calls

    calls = plan_calls({"calls": [
        {"tool": "birthdays_by_month", "field": "x", "days": 5},
        {"tool": "birthdays_by_month"},  # повтор
        {"tool": "stale_contacts", "days": 30, "limit": 0, "field": "city"},
        {"tool": "nope"},
        "строка",
        {"tool": "count_contacts_by", "field": "city"},
        {"tool": "contacts_added_over_time"},
        {"tool": "top_contacts_by_interactions"},
    ]})

    assert calls == [
        ("birthdays_by_month", {}),
        ("stale_contacts", {"days": 30}),
        ("count_contacts_by", {"field": "city"}),
    ]
    assert plan_calls({"calls": "мусор"}) == []


def test_capture_message_returns_preview_block_and_applies(client, anna, assistant, system_db):
    petya = _contact(client, anna, first_name="Пётр", last_name="Смирнов", city="Москва")
    chat = _chat(client, anna)
    sent = _send(client, anna, chat["id"], "встретил Петю, дочке 5 лет, переезжает в Дубай")
    job_id = sent["job"]["id"]

    assert _run(client, assistant, system_db, job_id, FakeLLM(chat_responder())) == "done"

    reply = _history(client, anna, chat["id"])["items"][-1]
    preview = next(b for b in reply["blocks"] if b["type"] == "capture_preview")
    assert preview["job_id"] == job_id and preview["result"]["contact_id"] == petya["id"] and preview["applied"] is None
    actions = [a["index"] for a in preview["result"]["actions"]]

    applied = client.post(f"{BASE}/jobs/{job_id}/apply", json={"actions": actions}, headers=anna)

    assert applied.status_code == 200, applied.text
    assert client.get(f"/api/contacts/{petya['id']}", headers=anna).json()["city"] == "Дубай"
    stored = next(b for b in _history(client, anna, chat["id"])["items"][-1]["blocks"] if b["type"] == "capture_preview")
    assert stored["applied"]["contact_id"] == petya["id"]
    again = client.post(f"{BASE}/jobs/{job_id}/apply", json={"actions": actions}, headers=anna)
    assert again.status_code == 409


def test_unavailable_model_fails_the_job_but_keeps_the_question(client, anna, assistant, system_db):
    chat = _chat(client, anna)
    sent = _send(client, anna, chat["id"], "Что такое привет?")

    with pytest.raises(Retry):  # модель недоступна — arq повторит задачу
        _run(client, assistant, system_db, sent["job"]["id"], FailingLLM(LLMUnavailableError("нет")))

    items = _history(client, anna, chat["id"])["items"]
    assert [m["role"] for m in items] == ["user"]


def test_chat_job_for_deleted_chat_fails_cleanly(client, anna, assistant, system_db):
    chat = _chat(client, anna)
    sent = _send(client, anna, chat["id"], "Сколько у меня контактов?")
    client.delete(f"{BASE}/chats/{chat['id']}", headers=anna)

    status = _run(client, assistant, system_db, sent["job"]["id"], FakeLLM(chat_responder()))

    assert status == "failed"
    assert client.get(f"{BASE}/jobs/{sent['job']['id']}", headers=anna).json()["error"]


# --- досье -----------------------------------------------------------------------------------


def dossier_responder(schema_name, system, user):
    assert schema_name == "dossier"
    assert "<контакт>" in user
    return {
        "who": "Юрист из Москвы",
        "how_we_know": "Познакомились на конференции",
        "key_facts": ["Дочке 5 лет", ""],
        "open_questions": ["Куда поедет в отпуск?"],
        "last_interactions": ["2026-02-01 — кофе"],
        "next_step": "Позвонить в пятницу",
    }


def test_dossier_job_stores_text_and_get_returns_it(client, anna, assistant, system_db):
    petya = _contact(client, anna, first_name="Пётр", city="Москва", notes="Юрист")
    assert client.get(f"{BASE}/dossier/{petya['id']}", headers=anna).status_code == 404

    started = client.post(f"{BASE}/dossier/{petya['id']}", headers=anna)
    assert started.status_code == 202 and started.json()["kind"] == "dossier"
    llm = FakeLLM(dossier_responder)
    assert _run(client, assistant, system_db, started.json()["id"], llm) == "done"

    got = client.get(f"{BASE}/dossier/{petya['id']}", headers=anna)
    assert got.status_code == 200
    body = got.json()
    assert body["contact_id"] == petya["id"] and body["model"] == "fake" and body["generated_at"]
    assert "Кто это: Юрист из Москвы" in body["text"] and "— Дочке 5 лет" in body["text"]
    assert "Следующий шаг: Позвонить в пятницу" in body["text"]
    assert "Пётр" in llm.calls[0]["user"] and "Юрист" in llm.calls[0]["user"]

    second = client.post(f"{BASE}/dossier/{petya['id']}", headers=anna)  # повторная генерация заменяет
    _run(client, assistant, system_db, second.json()["id"], FakeLLM(dossier_responder))
    assert client.get(f"{BASE}/dossier/{petya['id']}", headers=anna).status_code == 200


def test_dossier_includes_interactions_and_events_and_is_private(client, anna, boris, assistant, system_db):
    petya = _contact(client, anna, first_name="Пётр")
    started = client.post(f"{BASE}/dossier/{petya['id']}", headers=anna).json()
    user_db = client.portal.call(lambda: system_db["users"].find_one({"email": "anna@example.com"}))
    from app.auth import tenant_db

    db = tenant_db(system_db, user_db["db_name"])
    client.portal.call(lambda: db["interactions"].insert_one(
        {"contact_ids": [petya["id"]], "kind": "call", "occurred_at": datetime.now(timezone.utc) - timedelta(days=3), "note": "обсудили дачу"}
    ))
    client.portal.call(lambda: db["events"].insert_one(
        {"title": "Обед", "start": datetime.now(timezone.utc), "contact_ids": [petya["id"]]}
    ))
    llm = FakeLLM(dossier_responder)

    _run(client, assistant, system_db, started["id"], llm)

    assert "обсудили дачу" in llm.calls[0]["user"] and "Обед" in llm.calls[0]["user"]
    assert client.get(f"{BASE}/dossier/{petya['id']}", headers=boris).status_code == 404
    assert client.post(f"{BASE}/dossier/{petya['id']}", headers=boris).status_code == 404


def test_dossier_for_unknown_contact_is_404(client, anna):
    assert client.post(f"{BASE}/dossier/{'0' * 24}", headers=anna).status_code == 404
    assert client.post(f"{BASE}/dossier/плохой", headers=anna).status_code == 404
    assert client.get(f"{BASE}/dossier/плохой", headers=anna).status_code == 404


def test_dossier_job_for_missing_contact_fails(client, anna, assistant, system_db):
    petya = _contact(client, anna, first_name="Пётр")
    started = client.post(f"{BASE}/dossier/{petya['id']}", headers=anna).json()
    client.delete(f"/api/contacts/{petya['id']}", headers=anna)

    assert _run(client, assistant, system_db, started["id"], FakeLLM(dossier_responder)) == "failed"
