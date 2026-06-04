"""
Интеграционные тесты sync + import API.

Используем FastAPI TestClient + mongomock-motor (как в test_auth.py) и
мокируем все сетевые вызовы Microsoft (никаких реальных запросов к Graph).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.db import get_db


# ---------------------------------------------------------------------------
# Фикстуры: отдельная in-memory БД для этого модуля
# ---------------------------------------------------------------------------

_mock_client = AsyncMongoMockClient()
_mock_db = _mock_client["test_sync_crm"]


def override_get_db():
    return _mock_db


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def get_token(client: TestClient) -> str:
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth(client):
    return {"Authorization": f"Bearer {get_token(client)}"}


# ---------------------------------------------------------------------------
# Connect без Azure-кредов → понятная ошибка, не падение
# ---------------------------------------------------------------------------


class TestConnectWithoutCreds:
    def test_connect_microsoft_returns_501(self, client, auth):
        resp = client.post("/api/sync/connect/microsoft", headers=auth)
        assert resp.status_code == 501
        assert "Azure" in resp.json()["detail"]

    def test_connect_requires_auth(self, client):
        resp = client.post("/api/sync/connect/microsoft")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Импорт: upload → preview → confirm с детекцией дубля
# ---------------------------------------------------------------------------


class TestImportRoundTrip:
    def test_import_csv_detects_duplicate(self, client, auth):
        # 1. Сидируем существующий контакт с уникальным телефоном
        seed = client.post(
            "/api/contacts/",
            headers=auth,
            json={
                "first_name": "Дубль",
                "last_name": "Тестов",
                "phones": [{"value": "+79001112233", "label": "мобильный"}],
            },
        )
        assert seed.status_code == 201

        # 2. CSV: одна строка совпадает по телефону (8 вместо +7), вторая — новая
        csv_content = (
            "First Name,Last Name,Phone 1 - Value,Email 1 - Value\n"
            "Дубль,Тестов,89001112233,dubl@example.com\n"
            "Новый,Контакт,+79007778899,noviy@example.com\n"
        )
        up = client.post(
            "/api/import/upload",
            headers=auth,
            files={"file": ("contacts.csv", csv_content.encode("utf-8"), "text/csv")},
        )
        assert up.status_code == 200, up.text
        body = up.json()
        assert body["format"] == "csv"
        assert body["count"] == 2
        import_id = body["import_id"]

        # 3. Preview — один auto_merge (совпал телефон), один new
        prev = client.get(f"/api/import/{import_id}/preview", headers=auth)
        assert prev.status_code == 200, prev.text
        pbody = prev.json()
        assert pbody["total"] == 2
        assert pbody["auto_merge_count"] == 1
        assert pbody["new_count"] == 1
        # У auto_merge должен быть best_match с причиной "телефон"
        auto = next(i for i in pbody["items"] if i["classification"] == "auto_merge")
        assert any("телефон" in r for r in auto["best_match"]["reasons"])

        # 4. Confirm (по умолчанию: auto_merge→merge, new→create)
        conf = client.post(f"/api/import/{import_id}/confirm", headers=auth, json={})
        assert conf.status_code == 200, conf.text
        cbody = conf.json()
        assert cbody["created"] == 1
        assert cbody["merged"] == 1

        # 5. Новый контакт реально появился в базе
        found = client.get("/api/contacts/?q=noviy@example.com", headers=auth)
        assert found.status_code == 200
        assert len(found.json()) == 1

        # 6. Дубль слит: у исходного контакта появился email из CSV
        dub = client.get("/api/contacts/?q=dubl@example.com", headers=auth)
        assert len(dub.json()) == 1

    def test_preview_missing_session_404(self, client, auth):
        resp = client.get("/api/import/000000000000000000000000/preview", headers=auth)
        assert resp.status_code == 404

    def test_upload_requires_auth(self, client):
        resp = client.post(
            "/api/import/upload",
            files={"file": ("x.csv", b"First Name\nA\n", "text/csv")},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Microsoft sync с замоканным Graph
# ---------------------------------------------------------------------------


class TestMicrosoftSyncMocked:
    def test_sync_creates_contact_and_log(self, client, auth, monkeypatch):
        # Мок обмена кода на токены (callback)
        async def fake_exchange(code: str) -> dict:
            return {"access_token": "fake-access", "refresh_token": "fake-refresh", "expires_in": 3600}

        # Мок Graph: один контакт + пустой delta
        graph_contact = {
            "id": "OUTLOOK-1",
            "givenName": "Грейс",
            "surname": "Хоппер",
            "mobilePhone": "+79003334455",
            "emailAddresses": [{"address": "grace@example.com", "name": "Grace"}],
        }

        async def fake_fetch(access_token: str) -> list[dict]:
            return [graph_contact]

        async def fake_delta(access_token: str, delta_link=None):
            return [], "delta-link-xyz"

        monkeypatch.setattr("app.routers.sync.ms_exchange_code", fake_exchange)
        monkeypatch.setattr("app.routers.sync.fetch_outlook_contacts", fake_fetch)
        monkeypatch.setattr("app.routers.sync.delta_sync_contacts", fake_delta)

        # 1. Создаём подключение через callback (не следуем за редиректом)
        cb = client.get(
            "/api/sync/callback/microsoft",
            params={"code": "auth-code-123"},
            follow_redirects=False,
        )
        assert cb.status_code == 302
        assert "connected=microsoft" in cb.headers["location"]

        # 2. Находим созданное подключение
        conns = client.get("/api/sync/connections", headers=auth)
        assert conns.status_code == 200
        ms = [c for c in conns.json() if c["provider"] == "microsoft"]
        assert len(ms) >= 1
        conn_id = ms[0]["id"]

        # 3. Запускаем sync
        sync = client.post(f"/api/sync/contacts/{conn_id}", headers=auth)
        assert sync.status_code == 200, sync.text
        log = sync.json()
        assert log["stats"]["created"] == 1
        assert log["stats"]["errors"] == 0
        assert log["completed_at"] is not None

        # 4. Контакт из Outlook появился в базе
        found = client.get("/api/contacts/?q=grace@example.com", headers=auth)
        assert len(found.json()) == 1
        assert found.json()[0]["source"] == "outlook"

        # 5. Запись в sync_log существует
        logs = client.get("/api/sync/log", headers=auth)
        assert logs.status_code == 200
        assert any(l["action"] in ("full_sync", "delta_sync") for l in logs.json())

    def test_sync_unknown_connection_404(self, client, auth):
        resp = client.post("/api/sync/contacts/000000000000000000000000", headers=auth)
        assert resp.status_code == 404


class TestGoogleSyncMocked:
    def test_connect_google_without_creds_501(self, client, auth):
        resp = client.post("/api/sync/connect/google", headers=auth)
        assert resp.status_code == 501
        assert "Google" in resp.json()["detail"]

    def test_google_sync_creates_contact(self, client, auth, monkeypatch):
        async def fake_exchange(code: str) -> dict:
            return {"access_token": "g-access", "refresh_token": "g-refresh", "expires_in": 3600}

        person = {
            "resourceName": "people/c777",
            "names": [{"givenName": "Ада", "familyName": "Лавлейс"}],
            "emailAddresses": [{"value": "ada@example.com", "type": "home"}],
            "phoneNumbers": [{"value": "+79005556677", "type": "mobile"}],
        }

        async def fake_sync(access_token: str, sync_token=None):
            return [person], "sync-token-abc"

        monkeypatch.setattr("app.routers.sync.google_exchange_code", fake_exchange)
        monkeypatch.setattr("app.routers.sync.sync_google_contacts", fake_sync)

        cb = client.get(
            "/api/sync/callback/google",
            params={"code": "g-code"},
            follow_redirects=False,
        )
        assert cb.status_code == 302
        assert "connected=google" in cb.headers["location"]

        conns = client.get("/api/sync/connections", headers=auth)
        google = [c for c in conns.json() if c["provider"] == "google"]
        assert len(google) >= 1

        sync = client.post(f"/api/sync/contacts/{google[0]['id']}", headers=auth)
        assert sync.status_code == 200, sync.text
        assert sync.json()["stats"]["created"] == 1

        found = client.get("/api/contacts/?q=ada@example.com", headers=auth)
        assert len(found.json()) == 1
        assert found.json()[0]["source"] == "google"


class TestPushContact:
    def test_push_to_outlook_saves_external_id(self, client, auth, monkeypatch):
        # Подключение Microsoft через мок-callback
        async def fake_exchange(code: str) -> dict:
            return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

        async def fake_push(access_token: str, crm_contact: dict):
            return "NEW-OUTLOOK-ID"

        monkeypatch.setattr("app.routers.sync.ms_exchange_code", fake_exchange)
        monkeypatch.setattr("app.routers.sync.push_contact_to_outlook", fake_push)

        client.get("/api/sync/callback/microsoft", params={"code": "c"}, follow_redirects=False)
        conns = client.get("/api/sync/connections", headers=auth).json()
        conn_id = [c for c in conns if c["provider"] == "microsoft"][0]["id"]

        # Создаём контакт без external_ids.outlook
        created = client.post(
            "/api/contacts/",
            headers=auth,
            json={"first_name": "Толкатель", "last_name": "Тестов"},
        ).json()

        # Push
        resp = client.post(
            f"/api/sync/contacts/{conn_id}/push/{created['id']}", headers=auth
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["external_id"] == "NEW-OUTLOOK-ID"

        # external_ids.outlook сохранён в контакте
        got = client.get(f"/api/contacts/{created['id']}", headers=auth).json()
        assert got["external_ids"]["outlook"] == "NEW-OUTLOOK-ID"

    def test_push_unknown_contact_404(self, client, auth, monkeypatch):
        async def fake_exchange(code: str) -> dict:
            return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

        monkeypatch.setattr("app.routers.sync.ms_exchange_code", fake_exchange)
        client.get("/api/sync/callback/microsoft", params={"code": "c2"}, follow_redirects=False)
        conns = client.get("/api/sync/connections", headers=auth).json()
        conn_id = [c for c in conns if c["provider"] == "microsoft"][0]["id"]

        resp = client.post(
            f"/api/sync/contacts/{conn_id}/push/000000000000000000000000", headers=auth
        )
        assert resp.status_code == 404


class TestWebhooks:
    def test_validation_handshake(self, client):
        resp = client.post(
            "/api/webhooks/microsoft", params={"validationToken": "tok-12345"}
        )
        assert resp.status_code == 200
        assert resp.text == "tok-12345"
        assert resp.headers["content-type"].startswith("text/plain")

    def test_notification_triggers_background_sync(self, client, auth, monkeypatch):
        async def fake_exchange(code: str) -> dict:
            return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

        async def fake_fetch(access_token: str):
            return [{
                "id": "WH-1",
                "givenName": "Вебхук",
                "surname": "Контакт",
                "emailAddresses": [{"address": "webhook@example.com", "name": "x"}],
            }]

        async def fake_delta(access_token: str, delta_link=None):
            return [], "d"

        monkeypatch.setattr("app.routers.sync.ms_exchange_code", fake_exchange)
        monkeypatch.setattr("app.routers.sync.fetch_outlook_contacts", fake_fetch)
        monkeypatch.setattr("app.routers.sync.delta_sync_contacts", fake_delta)

        client.get("/api/sync/callback/microsoft", params={"code": "wh"}, follow_redirects=False)
        conns = client.get("/api/sync/connections", headers=auth).json()
        conn_id = [c for c in conns if c["provider"] == "microsoft"][-1]["id"]

        # Уведомление с clientState = connection_id
        resp = client.post(
            "/api/webhooks/microsoft",
            json={"value": [{"clientState": conn_id, "subscriptionId": "sub1"}]},
        )
        assert resp.status_code == 202

        # Фоновая задача в TestClient выполняется до возврата — контакт создан
        found = client.get("/api/contacts/?q=webhook@example.com", headers=auth)
        assert len(found.json()) == 1

        # Запись в логе с action=webhook
        logs = client.get("/api/sync/log", headers=auth).json()
        assert any(l["action"] == "webhook" for l in logs)

    def test_notification_unknown_state_is_202(self, client):
        resp = client.post(
            "/api/webhooks/microsoft",
            json={"value": [{"clientState": "000000000000000000000000"}]},
        )
        assert resp.status_code == 202
