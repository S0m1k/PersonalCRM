"""
ИИ-помощник через API: очередь → воркер → предпросмотр → применение.

Без настоящих Redis и модели: хранилище задач на fakeredis, очередь — список,
воркер вызываем руками (process_job) с моделью по сценарию.
"""

from __future__ import annotations

import pytest
from arq import Retry
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.ai import jobs
from app.ai.jobs import get_assistant
from app.ai.llm import LLMError, LLMUnavailableError
from app.ai.worker import process_job
from app.config import settings
from app.db import get_db
from app.main import app

from .ai_fakes import FailingLLM, FakeLLM, make_assistant, petya_responder

DOD_TEXT = "встретил Петю, дочке 5 лет, переезжает в Дубай"


@pytest.fixture
def system_db():
    return AsyncMongoMockClient()["test_assistant"]


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


def _contact(client, auth, **body) -> dict:
    resp = client.post("/api/contacts/", json=body, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _run(client, assistant, system_db, job_id: str, llm=None, **kwargs) -> str:
    """Выполнить задачу так, как это сделал бы воркер (в цикле событий TestClient)."""
    llm = llm or FakeLLM(petya_responder)
    return client.portal.call(lambda: process_job(assistant.store, system_db, llm, job_id, **kwargs))


def _capture(client, auth, text: str = DOD_TEXT) -> dict:
    resp = client.post("/api/assistant/capture", json={"text": text}, headers=auth)
    assert resp.status_code == 202, resp.text
    return resp.json()


def _job(client, auth, job_id: str):
    return client.get(f"/api/assistant/jobs/{job_id}", headers=auth)


class TestQueue:
    def test_capture_is_queued_with_position(self, client, anna, assistant):
        job = _capture(client, anna)

        assert job["status"] == "queued"
        assert job["position"] == 1
        assert assistant.queue.jobs == [job["id"]]
        assert "user_id" not in job and "input" not in job

    def test_per_user_cap(self, client, anna, boris, monkeypatch):
        monkeypatch.setattr(settings, "ai_user_max_queued", 2)
        _capture(client, anna)
        _capture(client, anna)

        third = client.post("/api/assistant/capture", json={"text": "ещё"}, headers=anna)
        other_user = client.post("/api/assistant/capture", json={"text": "ещё"}, headers=boris)

        assert third.status_code == 429
        assert other_user.status_code == 202

    def test_finished_job_frees_a_slot(self, client, anna, assistant, system_db, monkeypatch):
        monkeypatch.setattr(settings, "ai_user_max_queued", 1)
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        assert client.post("/api/assistant/capture", json={"text": "ещё"}, headers=anna).status_code == 202

    def test_cancel_queued_job_skips_model(self, client, anna, assistant, system_db):
        job = _capture(client, anna)
        llm = FakeLLM(petya_responder)

        cancelled = client.delete(f"/api/assistant/jobs/{job['id']}", headers=anna)
        status = _run(client, assistant, system_db, job["id"], llm=llm)

        assert cancelled.json()["status"] == "cancelled"
        assert status == "cancelled"
        assert llm.calls == []

    def test_requires_auth_and_valid_input(self, client, anna):
        assert client.post("/api/assistant/capture", json={"text": DOD_TEXT}).status_code == 401
        assert client.post("/api/assistant/capture", json={"text": "  "}, headers=anna).status_code == 422
        assert client.post("/api/assistant/ask", json={"question": "x" * 501}, headers=anna).status_code == 422

    def test_without_redis_assistant_is_unavailable(self, client, anna, monkeypatch):
        app.dependency_overrides.pop(get_assistant)
        monkeypatch.setattr(settings, "redis_url", None)
        monkeypatch.setattr(jobs, "_assistant", None)

        resp = client.post("/api/assistant/capture", json={"text": DOD_TEXT}, headers=anna)

        assert resp.status_code == 503

    def test_info(self, client, anna):
        info = client.get("/api/assistant/info", headers=anna).json()

        assert info["model"] == settings.llm_model
        assert info["fallback"] is None


class TestCapturePreviewThenApply:
    def test_dod_preview_has_field_closed_question_and_note(self, client, anna, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", last_name="Смирнов", city="Москва")
        job = _capture(client, anna)

        assert _run(client, assistant, system_db, job["id"]) == "done"
        result = _job(client, anna, job["id"]).json()["result"]

        assert result["contact_id"] == petya["id"]
        kinds = {a["type"]: a for a in result["actions"]}
        assert kinds["update_field"] | {"index": 0} == {
            "type": "update_field", "key": "city", "label": "Город", "old": "Москва", "new": "Дубай", "index": 0,
        }
        assert kinds["answer_question"]["question"] == "Сколько лет дочке?"
        assert kinds["add_note"]["text"] == "Встретились, переезжает в Дубай"

    def test_preview_changes_nothing_until_apply(self, client, anna, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", city="Москва")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        assert client.get(f"/api/contacts/{petya['id']}", headers=anna).json()["city"] == "Москва"
        assert client.get("/api/questions", headers=anna).json() == []

    def test_apply_selected_actions(self, client, anna, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", city="Москва")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        resp = client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0, 1, 2]}, headers=anna)

        assert resp.status_code == 200, resp.text
        assert all(r["ok"] for r in resp.json()["results"])
        card = client.get(f"/api/contacts/{petya['id']}", headers=anna).json()
        assert card["city"] == "Дубай"
        assert card["notes"].endswith("Встретились, переезжает в Дубай")
        questions = client.get("/api/questions", headers=anna).json()
        assert [(q["text"], q["status"], q["answer"], q["source"]) for q in questions] == [
            ("Сколько лет дочке?", "answered", "5 лет", "ai")
        ]
        assert _job(client, anna, job["id"]).json()["status"] == "applied"

    def test_unselected_actions_are_skipped(self, client, anna, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", city="Москва")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [2]}, headers=anna)

        assert client.get(f"/api/contacts/{petya['id']}", headers=anna).json()["city"] == "Москва"

    def test_apply_twice_is_rejected(self, client, anna, assistant, system_db):
        _contact(client, anna, first_name="Пётр")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])
        url = f"/api/assistant/jobs/{job['id']}/apply"

        assert client.post(url, json={"actions": [0]}, headers=anna).status_code == 200
        assert client.post(url, json={"actions": [0]}, headers=anna).status_code == 409

    def test_cannot_apply_before_done(self, client, anna):
        job = _capture(client, anna)

        resp = client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0]}, headers=anna)

        assert resp.status_code == 409

    def test_unknown_person_creates_contact_on_apply(self, client, anna, assistant, system_db):
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])
        result = _job(client, anna, job["id"]).json()["result"]

        resp = client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0]}, headers=anna)

        assert result["contact_id"] is None
        assert result["new_contact"] == {"first_name": "Пётр", "last_name": ""}
        created = resp.json()["created_contact"]
        assert created["name"] == "Пётр"
        assert client.get(f"/api/contacts/{created['id']}", headers=anna).json()["city"] == "Дубай"

    def test_apply_to_other_candidate(self, client, anna, assistant, system_db):
        _contact(client, anna, first_name="Пётр", last_name="Смирнов")
        other = _contact(client, anna, first_name="Пётр", last_name="Козлов")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0], "contact_id": other["id"]}, headers=anna
        )

        assert resp.json()["contact_id"] == other["id"]
        assert client.get(f"/api/contacts/{other['id']}", headers=anna).json()["city"] == "Дубай"

    def test_invalid_field_value_is_flagged_in_preview(self, client, anna, assistant, system_db):
        _contact(client, anna, first_name="Пётр")

        def responder(schema_name, system, user):
            data = petya_responder(schema_name, system, user)
            if schema_name == "capture":
                data["fields"] = [{"key": "birthday", "value": "весной"}]
            return data

        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"], llm=FakeLLM(responder))
        action = _job(client, anna, job["id"]).json()["result"]["actions"][0]

        assert action["type"] == "update_field"
        assert "ГГГГ-ММ-ДД" in action["error"]


def nameless_responder(schema_name, system, user):
    """Модель не нашла в записи имени человека (например, «купил квартиру в Дубае»)."""
    if schema_name == "person":
        return {"mention": "", "first_name": "", "last_name": ""}
    return petya_responder(schema_name, system, user)


class TestNewContactName:
    """Нового человека без имени в записи нельзя создать молча — имя вводит пользователь в предпросмотре."""

    def _nameless_preview(self, client, anna, assistant, system_db) -> dict:
        job = _capture(client, anna, text="Купил квартиру в Дубае, дочке пять лет")
        _run(client, assistant, system_db, job["id"], llm=FakeLLM(nameless_responder))
        return job

    def test_preview_has_no_name_for_new_contact(self, client, anna, assistant, system_db):
        job = self._nameless_preview(client, anna, assistant, system_db)

        result = _job(client, anna, job["id"]).json()["result"]

        assert result["contact_id"] is None
        assert result["new_contact"] is None

    def test_apply_without_any_name_is_422_and_stays_applicable(self, client, anna, assistant, system_db):
        job = self._nameless_preview(client, anna, assistant, system_db)
        url = f"/api/assistant/jobs/{job['id']}/apply"

        first = client.post(url, json={"actions": [0]}, headers=anna)
        retry = client.post(url, json={"actions": [0], "new_name": "Иван Петров"}, headers=anna)

        assert first.status_code == 422
        assert "имя" in first.json()["detail"].lower()
        assert retry.status_code == 200, retry.text  # задача не «сгорела» после ошибки

    def test_name_typed_by_user_creates_contact(self, client, anna, assistant, system_db):
        job = self._nameless_preview(client, anna, assistant, system_db)

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0], "new_name": "  Иван  Петров "}, headers=anna
        )

        assert resp.status_code == 200, resp.text
        created = resp.json()["created_contact"]
        assert created["name"] == "Иван Петров"
        card = client.get(f"/api/contacts/{created['id']}", headers=anna).json()
        assert (card["first_name"], card["last_name"]) == ("Иван", "Петров")
        assert card["city"] == "Дубай"

    def test_name_typed_by_user_overrides_model_guess(self, client, anna, assistant, system_db):
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])  # модель угадала «Пётр»

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0], "new_name": "Пётр Смирнов"}, headers=anna
        )

        assert resp.json()["created_contact"]["name"] == "Пётр Смирнов"

    def test_new_name_is_ignored_when_applying_to_existing_contact(self, client, anna, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", city="Москва")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0], "new_name": "Кто-то Другой"}, headers=anna
        )

        assert resp.json()["created_contact"] is None
        assert resp.json()["contact_id"] == petya["id"]
        assert len(client.get("/api/contacts/", headers=anna).json()) == 1

    def test_overlong_name_is_rejected(self, client, anna, assistant, system_db):
        job = self._nameless_preview(client, anna, assistant, system_db)

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0], "new_name": "Я" * 300}, headers=anna
        )

        assert resp.status_code == 422


CREATE_TEXT = "Создай контакт Иван Петров, телефон +7 900 123-45-67, компания Ромашка, директор"


def create_command_responder(schema_name, system, user):
    """Как на длинной команде: модель теряет человека, хотя имя стоит в тексте, и пишет заметку-эхо."""
    if schema_name == "person":
        return {"mention": "", "first_name": "", "last_name": ""}
    return {
        "contact_id": "",
        # name и phone — мусорные ключи модели: имя и телефон обрабатываются отдельно
        "fields": [
            {"key": "name", "value": "Иван Петров"},
            {"key": "phone", "value": "+7 900 123-45-67"},
            {"key": "company", "value": "Ромашка"},
            {"key": "position", "value": "директор"},
        ],
        "answers": [],
        "new_questions": [],
        "notes": ["Создан новый контакт Иван Петров, директор компании Ромашка"],
    }


def bare_command_responder(schema_name, system, user):
    """«Создай контакт Иван Петров» — модель находит имя, но предлагать ей нечего (или только эхо команды)."""
    if schema_name == "person":
        return {"mention": "Иван", "first_name": "Иван", "last_name": "Петров"}
    return {"contact_id": "", "fields": [], "answers": [], "new_questions": [], "notes": ["Создан новый контакт Иван Петров"]}


class TestCreateContactCommand:
    def _preview(self, client, anna, assistant, system_db, text=CREATE_TEXT) -> tuple[dict, dict]:
        job = _capture(client, anna, text=text)
        _run(client, assistant, system_db, job["id"], llm=FakeLLM(create_command_responder))
        return job, _job(client, anna, job["id"]).json()["result"]

    def test_name_is_taken_from_the_command_when_model_returns_nobody(self, client, anna, assistant, system_db):
        _, result = self._preview(client, anna, assistant, system_db)

        assert result["new_contact"] == {"first_name": "Иван", "last_name": "Петров"}
        assert result["contact_id"] is None

    def test_trace_shows_where_the_name_came_from(self, client, anna, assistant, system_db):
        _, result = self._preview(client, anna, assistant, system_db)

        assert result["trace"]["person"]["first_name"] == "Иван"
        assert result["trace"]["name_source"] == "command"

    def test_echo_note_is_dropped(self, client, anna, assistant, system_db):
        _, result = self._preview(client, anna, assistant, system_db)

        assert "add_note" not in [a["type"] for a in result["actions"]]

    def test_junk_name_and_phone_keys_from_model_are_dropped(self, client, anna, assistant, system_db):
        _, result = self._preview(client, anna, assistant, system_db)

        keys = [a["key"] for a in result["actions"] if a["type"] == "update_field"]

        assert keys == ["company", "position"]

    def test_phone_from_text_is_a_real_phone_action(self, client, anna, assistant, system_db):
        _, result = self._preview(client, anna, assistant, system_db)

        phones = [a for a in result["actions"] if a["type"] == "add_phone"]

        assert [p["value"] for p in phones] == ["+79001234567"]

    def test_email_from_text_is_a_real_email_action(self, client, anna, assistant, system_db):
        _, result = self._preview(
            client, anna, assistant, system_db, text="Создай контакт Иван Петров, почта Ivan.Petrov@Romashka.ru"
        )

        emails = [a for a in result["actions"] if a["type"] == "add_email"]

        assert [e["value"] for e in emails] == ["ivan.petrov@romashka.ru"]

    def test_apply_creates_the_contact_without_typing_the_name(self, client, anna, assistant, system_db):
        job, result = self._preview(client, anna, assistant, system_db)

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [a["index"] for a in result["actions"]]}, headers=anna
        )

        assert resp.status_code == 200, resp.text
        assert all(r["ok"] for r in resp.json()["results"])
        card = client.get(f"/api/contacts/{resp.json()['contact_id']}", headers=anna).json()
        assert (card["first_name"], card["last_name"]) == ("Иван", "Петров")
        assert (card["company"], card["position"]) == ("Ромашка", "директор")
        assert [(p["value"], p["label"]) for p in card["phones"]] == [("+79001234567", "мобильный")]
        assert card["custom_fields"] == []

    def test_same_phone_is_not_added_twice(self, client, anna, assistant, system_db):
        ivan = _contact(
            client, anna, first_name="Иван", last_name="Петров", phones=[{"value": "8 (900) 123-45-67", "label": "мобильный"}]
        )
        job, result = self._preview(client, anna, assistant, system_db)

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [a["index"] for a in result["actions"]]}, headers=anna
        )

        assert resp.status_code == 200, resp.text
        assert all(r["ok"] for r in resp.json()["results"])
        assert len(client.get(f"/api/contacts/{ivan['id']}", headers=anna).json()["phones"]) == 1

    def test_bare_command_offers_to_create_the_contact(self, client, anna, assistant, system_db):
        job = _capture(client, anna, text="Создай контакт Иван Петров")
        _run(client, assistant, system_db, job["id"], llm=FakeLLM(bare_command_responder))
        result = _job(client, anna, job["id"]).json()["result"]

        assert [(a["type"], a["name"]) for a in result["actions"]] == [("create_contact", "Иван Петров")]

        resp = client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0]}, headers=anna)

        assert resp.status_code == 200, resp.text
        assert resp.json()["created_contact"]["name"] == "Иван Петров"
        assert [(r["index"], r["ok"]) for r in resp.json()["results"]] == [(0, True)]

    def test_no_create_action_when_there_is_something_else_to_save(self, client, anna, assistant, system_db):
        _, result = self._preview(client, anna, assistant, system_db)

        assert "create_contact" not in [a["type"] for a in result["actions"]]

    def test_no_create_action_for_existing_person(self, client, anna, assistant, system_db):
        _contact(client, anna, first_name="Иван", last_name="Петров")
        job = _capture(client, anna, text="Создай контакт Иван Петров")

        _run(client, assistant, system_db, job["id"], llm=FakeLLM(bare_command_responder))

        assert _job(client, anna, job["id"]).json()["result"]["actions"] == []

    def test_existing_person_from_command_is_found_not_duplicated(self, client, anna, assistant, system_db):
        ivan = _contact(client, anna, first_name="Иван", last_name="Петров")

        _, result = self._preview(client, anna, assistant, system_db)

        assert result["contact_id"] == ivan["id"]

    def test_model_name_wins_over_the_command_rules(self, client, anna, assistant, system_db):
        job = _capture(client, anna, text="Создай контакт Иван Петров")
        _run(client, assistant, system_db, job["id"], llm=FakeLLM(petya_responder))  # модель вернула «Пётр»

        result = _job(client, anna, job["id"]).json()["result"]

        assert result["new_contact"] == {"first_name": "Пётр", "last_name": ""}
        assert result["trace"].get("name_source") != "command"


class TestCrossTenant:
    def test_other_user_cannot_see_cancel_or_apply(self, client, anna, boris, assistant, system_db):
        _contact(client, anna, first_name="Пётр")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        assert _job(client, boris, job["id"]).status_code == 404
        assert client.delete(f"/api/assistant/jobs/{job['id']}", headers=boris).status_code == 404
        apply = client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0]}, headers=boris)
        assert apply.status_code == 404

    def test_worker_reads_and_writes_only_owners_base(self, client, anna, boris, assistant, system_db):
        anna_petya = _contact(client, anna, first_name="Пётр", city="Москва")
        boris_petya = _contact(client, boris, first_name="Пётр", city="Казань")
        llm = FakeLLM(petya_responder)
        job = _capture(client, anna)

        _run(client, assistant, system_db, job["id"], llm=llm)
        client.post(f"/api/assistant/jobs/{job['id']}/apply", json={"actions": [0]}, headers=anna)

        # Модель видела только карточку Анны
        capture_call = next(c for c in llm.calls if c["schema_name"] == "capture")
        assert anna_petya["id"] in capture_call["user"]
        assert boris_petya["id"] not in capture_call["user"] and "Казань" not in capture_call["user"]
        assert client.get(f"/api/contacts/{anna_petya['id']}", headers=anna).json()["city"] == "Дубай"
        assert client.get(f"/api/contacts/{boris_petya['id']}", headers=boris).json()["city"] == "Казань"

    def test_apply_cannot_target_another_users_contact(self, client, anna, boris, assistant, system_db):
        boris_petya = _contact(client, boris, first_name="Пётр", city="Казань")
        job = _capture(client, anna)
        _run(client, assistant, system_db, job["id"])

        resp = client.post(
            f"/api/assistant/jobs/{job['id']}/apply",
            json={"actions": [0], "contact_id": boris_petya["id"]},
            headers=anna,
        )

        assert resp.status_code == 422
        assert client.get(f"/api/contacts/{boris_petya['id']}", headers=boris).json()["city"] == "Казань"


class TestWorkerFailures:
    def test_unavailable_model_is_retried_then_failed(self, client, anna, assistant, system_db):
        job = _capture(client, anna)
        down = FailingLLM(LLMUnavailableError("connection refused"))

        with pytest.raises(Retry):
            _run(client, assistant, system_db, job["id"], llm=down, job_try=1, max_tries=2)
        assert _job(client, anna, job["id"]).json()["status"] == "queued"

        assert _run(client, assistant, system_db, job["id"], llm=down, job_try=2, max_tries=2) == "failed"
        assert _job(client, anna, job["id"]).json()["error"] == "Модель недоступна, попробуйте позже"

    def test_bad_model_output_fails_without_retry(self, client, anna, assistant, system_db):
        job = _capture(client, anna)

        status = _run(client, assistant, system_db, job["id"], llm=FailingLLM(LLMError("Модель вернула не JSON")))

        assert status == "failed"
        assert _job(client, anna, job["id"]).json()["error"] == "Модель вернула не JSON"

    def test_timeout_marks_job_failed(self, client, anna, assistant, system_db):
        import asyncio

        class SlowLLM:
            name = "slow"

            async def complete_json(self, *args):
                await asyncio.sleep(5)

        job = _capture(client, anna)

        status = _run(client, assistant, system_db, job["id"], llm=SlowLLM(), timeout_s=0.05)

        assert status == "failed"
        assert _job(client, anna, job["id"]).json()["error"] == "Модель не успела ответить"

    def test_unexpected_error_hides_details(self, client, anna, assistant, system_db):
        job = _capture(client, anna)

        _run(client, assistant, system_db, job["id"], llm=FailingLLM(RuntimeError("secret internals")))

        assert _job(client, anna, job["id"]).json()["error"] == "Внутренняя ошибка помощника"

    def test_job_stuck_in_queue_expires(self, client, anna, assistant, monkeypatch):
        job = _capture(client, anna)
        monkeypatch.setattr(settings, "ai_queue_expires_s", -60)

        assert _job(client, anna, job["id"]).json()["status"] == "failed"


class TestAsk:
    def test_answer_uses_only_users_base(self, client, anna, boris, assistant, system_db):
        petya = _contact(client, anna, first_name="Пётр", city="Дубай")
        _contact(client, boris, first_name="Пётр", city="Казань")
        client.post("/api/questions", json={"contact_id": petya["id"], "text": "Как прошёл переезд?"}, headers=anna)
        seen: dict[str, str] = {}

        def responder(schema_name, system, user):
            if schema_name == "search_terms":
                return {"names": ["Пётр"], "keywords": []}
            seen["context"] = user
            return {"answer": "Спросить, как прошёл переезд", "contact_ids": [petya["id"], "чужой-id"]}

        resp = client.post("/api/assistant/ask", json={"question": "что я хотел спросить у Пети?"}, headers=anna)
        _run(client, assistant, system_db, resp.json()["id"], llm=FakeLLM(responder))
        result = _job(client, anna, resp.json()["id"]).json()["result"]

        assert result["answer"] == "Спросить, как прошёл переезд"
        assert result["contacts"] == [{"id": petya["id"], "name": "Пётр"}]
        assert "Как прошёл переезд?" in seen["context"] and "Казань" not in seen["context"]

    def test_ask_result_cannot_be_applied(self, client, anna, assistant, system_db):
        resp = client.post("/api/assistant/ask", json={"question": "кто в Дубае?"}, headers=anna)

        def responder(schema_name, system, user):
            if schema_name == "search_terms":
                return {"names": [], "keywords": ["Дубай"]}
            return {"answer": "Никого", "contact_ids": []}

        _run(client, assistant, system_db, resp.json()["id"], llm=FakeLLM(responder))
        apply = client.post(f"/api/assistant/jobs/{resp.json()['id']}/apply", json={"actions": [0]}, headers=anna)

        assert apply.status_code == 409
