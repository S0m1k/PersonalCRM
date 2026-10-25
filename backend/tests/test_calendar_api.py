"""
Календарь: CRUD /api/calendar/events, часовые пояса, привязка к людям, вопросы «на встрече»,
изоляция пользователей. Провайдеры здесь не участвуют (см. test_calendar_sync.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app
from app.ratelimit import find_rule

EVENTS = "/api/calendar/events"


@pytest.fixture
def client():
    system_db = AsyncMongoMockClient()["test_calendar_api"]
    app.dependency_overrides[get_db] = lambda: system_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def register(client, email: str) -> dict:
    resp = client.post("/api/auth/register", json={"email": email, "password": "password-123"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client, "anna@example.com")


def contact(client, auth, first_name: str, **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": first_name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def event(client, auth, **fields) -> dict:
    body = {"title": "Встреча", "start": "2026-11-02T10:00:00", "timezone": "Europe/Moscow", **fields}
    resp = client.post(EVENTS, json=body, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCrud:
    def test_naive_time_is_read_in_event_timezone(self, client, auth):
        created = event(client, auth)

        assert created["start"].startswith("2026-11-02T07:00:00")  # 10:00 МСК = 07:00 UTC
        assert created["end"].startswith("2026-11-02T08:00:00")  # без конца — час
        assert created["source"] == "crm"

    def test_range_query_returns_overlapping_events(self, client, auth):
        event(client, auth, title="Утро", start="2026-11-02T09:00:00Z", end="2026-11-02T10:00:00Z")
        event(client, auth, title="Завтра", start="2026-11-03T09:00:00Z", end="2026-11-03T10:00:00Z")

        day = client.get(
            EVENTS, params={"start": "2026-11-02T00:00:00Z", "end": "2026-11-03T00:00:00Z"}, headers=auth
        ).json()

        assert [e["title"] for e in day] == ["Утро"]

    def test_update_and_delete(self, client, auth):
        created = event(client, auth)

        patched = client.patch(
            f"{EVENTS}/{created['id']}", json={"title": "Обед", "start": "2026-11-02T13:00:00"}, headers=auth
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["title"] == "Обед"
        assert patched.json()["start"].startswith("2026-11-02T10:00:00")

        assert client.delete(f"{EVENTS}/{created['id']}", headers=auth).status_code == 204
        assert client.get(f"{EVENTS}/{created['id']}", headers=auth).status_code == 404

    def test_all_day_event_covers_whole_days(self, client, auth):
        created = event(client, auth, start="2026-11-05", all_day=True)

        assert created["start"].startswith("2026-11-05T00:00:00")
        assert created["end"].startswith("2026-11-06T00:00:00")

    @pytest.mark.parametrize(
        "fields",
        [
            {"end": "2026-11-02T09:00:00"},  # раньше начала
            {"timezone": "Mars/Olympus"},
            {"title": ""},
        ],
    )
    def test_invalid_input_is_422(self, client, auth, fields):
        body = {"title": "Встреча", "start": "2026-11-02T10:00:00", **fields}
        assert client.post(EVENTS, json=body, headers=auth).status_code == 422

    def test_unknown_contact_is_404(self, client, auth):
        resp = client.post(
            EVENTS,
            json={"title": "x", "start": "2026-11-02T10:00:00Z", "contact_ids": ["000000000000000000000000"]},
            headers=auth,
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        assert client.get(EVENTS).status_code == 401

    def test_writes_have_own_rate_limit_rule(self):
        assert find_rule("POST", EVENTS).name == "calendar"
        assert find_rule("GET", EVENTS).name == "read"


class TestContactLinks:
    def test_attendee_email_and_phone_link_contacts(self, client, auth):
        petya = contact(client, auth, "Петя", emails=[{"value": "Petya@Example.com", "label": "work"}])
        vasya = contact(client, auth, "Вася", phones=[{"value": "+7 (900) 111-22-33", "label": "mob"}])

        created = event(
            client,
            auth,
            attendees=[{"email": "petya@example.com"}, {"phone": "89001112233"}, {"email": "stranger@x.io"}],
        )

        assert set(created["contact_ids"]) == {petya["id"], vasya["id"]}
        assert {c["name"] for c in created["contacts"]} == {"Петя", "Вася"}

    def test_manual_unlink_survives_attendee_changes(self, client, auth):
        petya = contact(client, auth, "Петя", emails=[{"value": "petya@example.com", "label": "work"}])
        masha = contact(client, auth, "Маша")
        created = event(client, auth, attendees=[{"email": "petya@example.com"}])

        # Отвязали Петю, привязали Машу вручную
        client.patch(f"{EVENTS}/{created['id']}", json={"contact_ids": [masha["id"]]}, headers=auth)
        again = client.patch(
            f"{EVENTS}/{created['id']}",
            json={"attendees": [{"email": "petya@example.com"}, {"email": "new@x.io"}]},
            headers=auth,
        ).json()

        assert again["contact_ids"] == [masha["id"]]
        assert petya["id"] not in again["contact_ids"]

    def test_contact_filter_and_delete_unlinks(self, client, auth):
        petya = contact(client, auth, "Петя")
        created = event(client, auth, contact_ids=[petya["id"]])
        event(client, auth, title="Без Пети")

        mine = client.get(EVENTS, params={"contact_id": petya["id"]}, headers=auth).json()
        assert [e["id"] for e in mine] == [created["id"]]

        client.delete(f"/api/contacts/{petya['id']}", headers=auth)
        assert client.get(f"{EVENTS}/{created['id']}", headers=auth).json()["contact_ids"] == []


class TestQuestions:
    def test_event_shows_open_next_meeting_questions_of_linked_people(self, client, auth):
        petya = contact(client, auth, "Петя")
        ask = {"contact_id": petya["id"], "ask_at": "next_meeting"}
        client.post("/api/questions", json={**ask, "text": "Как отпуск?"}, headers=auth)
        client.post("/api/questions", json={"contact_id": petya["id"], "text": "Когда-нибудь"}, headers=auth)
        answered = client.post("/api/questions", json={**ask, "text": "Старый"}, headers=auth).json()
        client.patch(f"/api/questions/{answered['id']}", json={"status": "answered"}, headers=auth)

        created = event(client, auth, contact_ids=[petya["id"]])

        assert [(q["text"], q["contact_name"]) for q in created["questions"]] == [("Как отпуск?", "Петя")]


class TestIsolation:
    def test_other_user_cannot_see_or_change_events(self, client, auth):
        created = event(client, auth)
        boris = register(client, "boris@example.com")

        assert client.get(EVENTS, headers=boris).json() == []
        assert client.get(f"{EVENTS}/{created['id']}", headers=boris).status_code == 404
        assert client.patch(f"{EVENTS}/{created['id']}", json={"title": "x"}, headers=boris).status_code == 404
        assert client.delete(f"{EVENTS}/{created['id']}", headers=boris).status_code == 404
        assert client.get(f"{EVENTS}/{created['id']}", headers=auth).json()["title"] == "Встреча"

    def test_cannot_link_other_users_contact(self, client, auth):
        boris = register(client, "boris@example.com")
        foreign = contact(client, boris, "Чужой")

        resp = client.post(
            EVENTS, json={"title": "x", "start": "2026-11-02T10:00:00Z", "contact_ids": [foreign["id"]]}, headers=auth
        )
        assert resp.status_code == 404
