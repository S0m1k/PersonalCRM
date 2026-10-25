"""
Синхронизация календарей с замоканным HTTP Microsoft Graph и Google Calendar
(httpx.MockTransport вместо сети): чтение изменений, инкрементальный sync, запись событий,
переподключение старых подключений без прав на календарь, изоляция пользователей.
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app
from app.repositories import sync as sync_repo
from app.sync import scheduler as sch

EVENTS = "/api/calendar/events"
MS_SCOPE = "Contacts.ReadWrite Calendars.ReadWrite User.Read profile openid"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/contacts https://www.googleapis.com/auth/calendar.events"


@pytest.fixture
def system_db():
    return AsyncMongoMockClient()["test_calendar_sync"]


@pytest.fixture
def client(system_db):
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


class FakeApi:
    """Запоминает запросы и отвечает по очереди заданными ответами для (метод, кусок пути)."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.routes: list[tuple[str, str, list]] = []

    def on(self, method: str, path_part: str, *responses) -> "FakeApi":
        self.routes.append((method, path_part, list(responses)))
        return self

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for method, part, responses in self.routes:
            if request.method == method and part in str(request.url):
                status, body = responses.pop(0) if len(responses) > 1 else responses[0]
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"error": "no route"})

    def bodies(self, method: str) -> list[dict]:
        return [json.loads(r.content) for r in self.requests if r.method == method]


def mock_http(monkeypatch, provider: str, api: FakeApi) -> None:
    module = "calendar_microsoft" if provider == "microsoft" else "calendar_google"
    monkeypatch.setattr(f"app.sync.{module}._http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(api)))


def connect(client, auth, monkeypatch, provider: str, scope, connection_id: str | None = None) -> str:
    """Подключить аккаунт через callback (как браузер). Возвращает id подключения."""
    prefix = "ms" if provider == "microsoft" else "google"
    monkeypatch.setattr(f"app.routers.sync.{prefix}_configured", lambda: True)
    monkeypatch.setattr(f"app.routers.sync.{prefix}_authorize_url", lambda state: "https://login.example")

    async def fake_exchange(code: str) -> dict:
        data = {"access_token": f"{provider}-access", "refresh_token": "rt", "expires_in": 3600}
        return {**data, "scope": scope} if scope else data

    monkeypatch.setattr(f"app.routers.sync.{prefix}_exchange_code", fake_exchange)
    params = {"connection_id": connection_id} if connection_id else {}
    state = client.post(f"/api/sync/connect/{provider}", params=params, headers=auth).json()["state"]
    cb = client.get(f"/api/sync/callback/{provider}", params={"code": "c", "state": state}, follow_redirects=False)
    assert cb.status_code == 302 and "connected=" in cb.headers["location"], cb.headers.get("location")
    conns = [c for c in client.get("/api/sync/connections", headers=auth).json() if c["provider"] == provider]
    return conns[-1]["id"]


def graph_event(event_id: str, subject: str, attendee: str = "", **extra) -> dict:
    return {
        "id": event_id,
        "subject": subject,
        "start": {"dateTime": "2026-11-02T07:00:00.0000000", "timeZone": "UTC"},
        "end": {"dateTime": "2026-11-02T08:00:00.0000000", "timeZone": "UTC"},
        "originalStartTimeZone": "Europe/Moscow",
        "body": {"contentType": "html", "content": "<p>Обсудить&nbsp;план</p>"},
        "location": {"displayName": "Кафе"},
        "organizer": {"emailAddress": {"address": "me@example.com", "name": "Я"}},
        "attendees": [{"emailAddress": {"address": attendee, "name": "Петя"}, "status": {"response": "accepted"}}]
        if attendee
        else [],
        "webLink": "https://outlook.example/1",
        **extra,
    }


class TestMicrosoftCalendar:
    def test_full_then_delta_sync(self, client, auth, monkeypatch):
        petya = client.post(
            "/api/contacts/",
            json={"first_name": "Петя", "emails": [{"value": "petya@example.com", "label": "work"}]},
            headers=auth,
        ).json()
        conn_id = connect(client, auth, monkeypatch, "microsoft", MS_SCOPE)
        api = FakeApi().on(
            "GET",
            "calendarView/delta",
            (200, {"value": [graph_event("E1", "Кофе с Петей", "petya@example.com")], "@odata.nextLink": "https://graph.microsoft.com/v1.0/next-page"}),
        ).on(
            "GET",
            "next-page",
            (200, {"value": [graph_event("E2", "Отменили", isCancelled=True)], "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-1"}),
        )
        mock_http(monkeypatch, "microsoft", api)

        log = client.post(f"/api/sync/calendar/{conn_id}", headers=auth)
        assert log.status_code == 200, log.text
        assert log.json()["stats"]["created"] == 1
        assert log.json()["type"] == "calendar"
        first = api.requests[0]
        assert "startDateTime" in str(first.url) and 'outlook.timezone="UTC"' in first.headers["Prefer"]

        events = client.get(EVENTS, headers=auth).json()
        assert len(events) == 1
        got = events[0]
        assert (got["title"], got["source"], got["description"]) == ("Кофе с Петей", "microsoft", "Обсудить план")
        assert got["contact_ids"] == [petya["id"]]
        assert got["start"].startswith("2026-11-02T07:00:00")

        # Второй раз — по deltaLink: событие изменилось и затем удалено
        api.on(
            "GET",
            "delta-1",
            (200, {"value": [{"id": "E1", "@removed": {"reason": "deleted"}}], "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta-2"}),
        )
        log = client.post(f"/api/sync/calendar/{conn_id}", headers=auth).json()
        assert log["action"] == "delta_sync"
        assert log["stats"]["deleted"] == 1
        assert client.get(EVENTS, headers=auth).json() == []

    def test_legacy_connection_asks_for_reconsent(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "microsoft", scope=None)  # как до Sprint 7
        conns = client.get("/api/sync/connections", headers=auth).json()
        assert conns[0]["calendar_access"] is False

        resp = client.post(f"/api/sync/calendar/{conn_id}", headers=auth)
        assert resp.status_code == 403
        assert "Переподключите" in resp.json()["detail"]

        # Переподключение того же подключения: права добавились, нового подключения нет
        same_id = connect(client, auth, monkeypatch, "microsoft", MS_SCOPE, connection_id=conn_id)
        conns = client.get("/api/sync/connections", headers=auth).json()
        assert same_id == conn_id and len(conns) == 1
        assert conns[0]["calendar_access"] is True and conns[0]["sync_calendar"] is True

    def test_provider_403_marks_connection_for_reconsent(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "microsoft", MS_SCOPE)
        mock_http(monkeypatch, "microsoft", FakeApi().on("GET", "calendarView", (403, {"error": "denied"})))

        assert client.post(f"/api/sync/calendar/{conn_id}", headers=auth).status_code == 403
        assert client.get("/api/sync/connections", headers=auth).json()[0]["calendar_access"] is False

    def test_reconnect_with_foreign_connection_id_is_404(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "microsoft", MS_SCOPE)
        boris = register(client, "boris@example.com")

        resp = client.post("/api/sync/connect/microsoft", params={"connection_id": conn_id}, headers=boris)
        assert resp.status_code == 404

    def test_push_event_with_questions_opt_in(self, client, auth, monkeypatch):
        petya = client.post("/api/contacts/", json={"first_name": "Петя"}, headers=auth).json()
        client.post(
            "/api/questions",
            json={"contact_id": petya["id"], "text": "Как отпуск?", "ask_at": "next_meeting"},
            headers=auth,
        )
        conn_id = connect(client, auth, monkeypatch, "microsoft", MS_SCOPE)
        created_remote = graph_event("NEW-1", "Встреча")
        api = FakeApi().on("POST", "/me/events", (201, created_remote)).on("PATCH", "/me/events/NEW-1", (200, created_remote))
        mock_http(monkeypatch, "microsoft", api)

        resp = client.post(
            EVENTS,
            json={
                "title": "Встреча",
                "start": "2026-11-02T10:00:00",
                "timezone": "Europe/Moscow",
                "description": "Повестка",
                "attendees": [{"email": "petya@example.com"}],
                "contact_ids": [petya["id"]],
                "push_questions": True,
                "connection_id": conn_id,
            },
            headers=auth,
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert (created["external_id"], created["source"]) == ("NEW-1", "microsoft")

        body = api.bodies("POST")[0]
        assert "attendees" not in body  # приглашения от имени пользователя не рассылаем
        assert body["start"] == {"dateTime": "2026-11-02T07:00:00", "timeZone": "UTC"}
        assert body["body"]["content"].startswith("Повестка")
        assert "Петя: Как отпуск?" in body["body"]["content"]

        # Без push_questions блок вопросов убирается
        client.patch(f"{EVENTS}/{created['id']}", json={"push_questions": False}, headers=auth)
        assert api.bodies("PATCH")[-1]["body"]["content"] == "Повестка"

    def test_failed_push_keeps_nothing(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "microsoft", MS_SCOPE)
        mock_http(monkeypatch, "microsoft", FakeApi().on("POST", "/me/events", (500, {"error": "boom"})))

        resp = client.post(
            EVENTS, json={"title": "x", "start": "2026-11-02T10:00:00Z", "connection_id": conn_id}, headers=auth
        )
        assert resp.status_code == 502
        assert client.get(EVENTS, headers=auth).json() == []


class TestGoogleCalendar:
    def google_event(self, event_id: str, **extra) -> dict:
        return {
            "id": event_id,
            "status": "confirmed",
            "summary": "Созвон",
            "start": {"dateTime": "2026-11-03T12:00:00+03:00", "timeZone": "Europe/Moscow"},
            "end": {"dateTime": "2026-11-03T13:00:00+03:00"},
            "attendees": [
                {"email": "me@example.com", "self": True},
                {"email": "ada@example.com", "displayName": "Ада", "responseStatus": "accepted"},
            ],
            "htmlLink": "https://calendar.example/1",
            "etag": '"1"',
            **extra,
        }

    def test_sync_token_flow_and_expired_token(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "google", GOOGLE_SCOPE)
        api = FakeApi().on(
            "GET",
            "events",
            (200, {"items": [self.google_event("G1")], "nextPageToken": "p2"}),
            (200, {"items": [self.google_event("G2", start={"date": "2026-11-04"}, end={"date": "2026-11-05"})], "nextSyncToken": "sync-1"}),
            (410, {"error": "gone"}),  # syncToken протух
            (200, {"items": [self.google_event("G1", status="cancelled")], "nextSyncToken": "sync-2"}),
        )
        mock_http(monkeypatch, "google", api)

        log = client.post(f"/api/sync/calendar/{conn_id}", headers=auth).json()
        assert log["stats"]["created"] == 2
        assert "timeMin" in str(api.requests[0].url) and "pageToken=p2" in str(api.requests[1].url)
        events = {e["external_id"]: e for e in client.get(EVENTS, headers=auth).json()}
        assert events["G1"]["start"].startswith("2026-11-03T09:00:00")
        assert [a["email"] for a in events["G1"]["attendees"]] == ["ada@example.com"]
        assert events["G2"]["all_day"] is True

        log = client.post(f"/api/sync/calendar/{conn_id}", headers=auth).json()
        assert "syncToken=sync-1" in str(api.requests[2].url)
        assert "timeMin" in str(api.requests[3].url)  # после 410 — полная синхронизация
        assert log["stats"]["deleted"] == 1
        assert [e["external_id"] for e in client.get(EVENTS, headers=auth).json()] == ["G2"]

    def test_update_and_delete_go_to_google(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "google", GOOGLE_SCOPE)
        api = (
            FakeApi()
            .on("GET", "events", (200, {"items": [self.google_event("G1")], "nextSyncToken": "s"}))
            .on("PATCH", "events/G1", (200, self.google_event("G1", summary="Новое")))
            .on("DELETE", "events/G1", (204, {}))
        )
        mock_http(monkeypatch, "google", api)
        client.post(f"/api/sync/calendar/{conn_id}", headers=auth)
        event_id = client.get(EVENTS, headers=auth).json()[0]["id"]

        patched = client.patch(f"{EVENTS}/{event_id}", json={"title": "Новое"}, headers=auth)
        assert patched.status_code == 200, patched.text
        assert api.bodies("PATCH")[0]["summary"] == "Новое"
        assert api.bodies("PATCH")[0]["start"]["dateTime"].startswith("2026-11-03T09:00:00")

        assert client.delete(f"{EVENTS}/{event_id}", headers=auth).status_code == 204
        assert any(r.method == "DELETE" for r in api.requests)

    def test_disconnect_removes_calendar_events(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "google", GOOGLE_SCOPE)
        mock_http(monkeypatch, "google", FakeApi().on("GET", "events", (200, {"items": [self.google_event("G1")]})))
        client.post(f"/api/sync/calendar/{conn_id}", headers=auth)

        client.delete(f"/api/sync/connections/{conn_id}", headers=auth)
        assert client.get(EVENTS, headers=auth).json() == []


class TestIsolationAndScheduler:
    def test_other_user_cannot_sync_or_push_to_my_connection(self, client, auth, monkeypatch):
        conn_id = connect(client, auth, monkeypatch, "google", GOOGLE_SCOPE)
        boris = register(client, "boris@example.com")

        assert client.post(f"/api/sync/calendar/{conn_id}", headers=boris).status_code == 404
        resp = client.post(
            EVENTS, json={"title": "x", "start": "2026-11-02T10:00:00Z", "connection_id": conn_id}, headers=boris
        )
        assert resp.status_code == 404

    async def test_scheduler_syncs_only_connections_with_calendar_access(self, system_db, monkeypatch):
        monkeypatch.setattr(sch, "get_db", lambda: system_db)
        calls: list[str] = []

        async def fake_run(db, conn, stats, errors):
            calls.append(conn.provider)
            stats.created += 1

        monkeypatch.setattr(sch, "run_calendar_sync", fake_run)
        monkeypatch.setattr(sch, "user_dbs", _async_value([system_db]))
        for provider, scope, enabled in (
            ("google", GOOGLE_SCOPE, True),
            ("microsoft", None, True),  # старое подключение без прав
            ("microsoft", MS_SCOPE, False),  # календарь выключен
        ):
            await sync_repo.create_connection(
                system_db, provider=provider, access_token="a", sync_contacts=False, sync_calendar=enabled, scopes=scope
            )

        await sch.periodic_sync()

        assert calls == ["google"]
        logs = await sync_repo.list_logs(system_db)
        assert [(log.type, log.stats.created) for log in logs] == [("calendar", 1)]


def _async_value(value):
    async def fn():
        return value

    return fn
