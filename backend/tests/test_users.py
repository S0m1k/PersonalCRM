"""
Пользователи: регистрация, вход, изоляция данных, пароли, перенос однопользовательской версии.

Данные каждого пользователя — в отдельной базе, поэтому главное, что проверяем:
один пользователь не видит и не меняет данные другого ни через API, ни через CardDAV,
ни через callback OAuth и вебхуки (там нет JWT).
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.config import settings
from app.db import get_db
from app.main import app

BOOK = "/dav/addressbooks/contacts/"


@pytest.fixture
def system_db():
    return AsyncMongoMockClient()["test_users"]


@pytest.fixture
def client(system_db):
    app.dependency_overrides[get_db] = lambda: system_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email: str, password: str = "password-123", name: str = "") -> dict:
    resp = client.post("/api/auth/register", json={"email": email, "password": password, "name": name})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _basic(login: str, password: str) -> dict:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _contact(client, auth, first_name: str) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": first_name}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestRegistration:
    def test_register_returns_working_token(self, client):
        auth = _register(client, "Anna@Example.com ", name="Анна")

        me = client.get("/api/auth/me", headers=auth).json()

        assert me["email"] == "anna@example.com"
        assert me["name"] == "Анна"
        assert not {"password_hash", "carddav_secret", "db_name"} & me.keys()

    def test_duplicate_email_is_rejected_case_insensitive(self, client):
        _register(client, "anna@example.com")

        resp = client.post("/api/auth/register", json={"email": "ANNA@example.com", "password": "password-123"})

        assert resp.status_code == 409

    @pytest.mark.parametrize(
        "body",
        [
            {"email": "not-an-email", "password": "password-123"},
            {"email": "a@b.co", "password": "short"},
            {"email": "a@b.co", "password": "x" * 129},
        ],
    )
    def test_invalid_input_is_422(self, client, body):
        assert client.post("/api/auth/register", json=body).status_code == 422

    def test_user_cap(self, client, monkeypatch):
        monkeypatch.setattr(settings, "max_users", 2)
        _register(client, "a@example.com")
        _register(client, "b@example.com")

        resp = client.post("/api/auth/register", json={"email": "c@example.com", "password": "password-123"})

        assert resp.status_code == 403

    def test_closed_registration(self, client, monkeypatch):
        monkeypatch.setattr(settings, "registration_open", False)

        resp = client.post("/api/auth/register", json={"email": "a@b.co", "password": "password-123"})

        assert resp.status_code == 403

    def test_login_with_email(self, client):
        _register(client, "anna@example.com", password="password-123")

        ok = client.post("/api/auth/login/json", json={"username": "ANNA@example.com", "password": "password-123"})
        bad = client.post("/api/auth/login/json", json={"username": "anna@example.com", "password": "wrong-pass"})
        unknown = client.post("/api/auth/login/json", json={"username": "nobody@example.com", "password": "x"})

        assert ok.status_code == 200
        assert bad.status_code == 401
        assert unknown.status_code == 401
        assert bad.json() == unknown.json()

    def test_token_of_unknown_user_is_rejected(self, client):
        from app.auth import create_access_token

        token = create_access_token(subject="64b000000000000000000000")

        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


class TestIsolation:
    def test_users_do_not_see_each_others_contacts(self, client):
        anna = _register(client, "anna@example.com")
        boris = _register(client, "boris@example.com")
        secret = _contact(client, anna, "Секретный")

        assert client.get("/api/contacts/", headers=boris).json() == []
        assert client.get(f"/api/contacts/{secret['id']}", headers=boris).status_code == 404
        assert client.patch(
            f"/api/contacts/{secret['id']}", json={"first_name": "Взлом"}, headers=boris
        ).status_code == 404
        assert client.delete(f"/api/contacts/{secret['id']}", headers=boris).status_code == 404
        assert client.get(f"/api/contacts/{secret['id']}", headers=anna).json()["first_name"] == "Секретный"

    def test_each_user_gets_own_templates_and_questions(self, client):
        anna = _register(client, "anna@example.com")
        boris = _register(client, "boris@example.com")
        contact = _contact(client, anna, "Пётр")
        client.post("/api/questions", json={"contact_id": contact["id"], "text": "Как дела?"}, headers=anna)
        custom = client.post("/api/templates", json={"name": "Только у Анны", "fields": []}, headers=anna)
        assert custom.status_code == 201

        boris_templates = [t["name"] for t in client.get("/api/templates", headers=boris).json()]

        assert boris_templates, "встроенные шаблоны создаются и у нового пользователя"
        assert "Только у Анны" not in boris_templates
        assert client.get("/api/questions", headers=boris).json() == []

    def test_new_user_data_lives_in_separate_database(self, client, system_db):
        anna = _register(client, "anna@example.com")
        _contact(client, anna, "Пётр")

        user = client.portal.call(system_db["users"].find_one, {"email": "anna@example.com"})

        assert user["db_name"] != system_db.name
        assert client.portal.call(system_db.client[user["db_name"]]["contacts"].count_documents, {}) == 1
        assert client.portal.call(system_db["contacts"].count_documents, {}) == 0

    def test_carddav_shows_only_own_contacts(self, client):
        anna = _register(client, "anna@example.com")
        boris = _register(client, "boris@example.com")
        _contact(client, anna, "Пётр")
        anna_dav = client.post("/api/auth/carddav-password", headers=anna).json()
        boris_dav = client.post("/api/auth/carddav-password", headers=boris).json()

        def cards(creds) -> int:
            resp = client.request(
                "PROPFIND", BOOK, headers={**_basic(creds["username"], creds["password"]), "Depth": "1"}
            )
            assert resp.status_code == 207
            return resp.text.count(".vcf")

        assert cards(anna_dav) == 1
        assert cards(boris_dav) == 0
        # Пароль одного пользователя не подходит к логину другого
        mixed = _basic("boris@example.com", anna_dav["password"])
        assert client.request("PROPFIND", BOOK, headers={**mixed, "Depth": "0"}).status_code == 401


class TestPasswords:
    def test_change_password(self, client):
        auth = _register(client, "anna@example.com", password="password-123")

        wrong = client.post(
            "/api/auth/password", json={"current_password": "nope-nope", "new_password": "new-password-1"}, headers=auth
        )
        ok = client.post(
            "/api/auth/password",
            json={"current_password": "password-123", "new_password": "new-password-1"},
            headers=auth,
        )

        assert wrong.status_code == 400
        assert ok.status_code == 200
        # Старый токен (другие устройства) отозван, новый из ответа работает
        assert client.get("/api/auth/me", headers=auth).status_code == 401
        new_auth = {"Authorization": f"Bearer {ok.json()['access_token']}"}
        assert client.get("/api/auth/me", headers=new_auth).status_code == 200
        login = lambda pw: client.post(  # noqa: E731
            "/api/auth/login/json", json={"username": "anna@example.com", "password": pw}
        ).status_code
        assert login("password-123") == 401
        assert login("new-password-1") == 200

    def test_password_longer_than_bcrypt_limit_is_rejected(self, client):
        # 40 кириллических букв = 80 байт: bcrypt молча обрезал бы до 72
        resp = client.post("/api/auth/register", json={"email": "a@b.co", "password": "я" * 40})

        assert resp.status_code == 422

    def test_carddav_password_is_shown_once_and_stored_hashed(self, client, system_db):
        auth = _register(client, "anna@example.com")

        issued = client.post("/api/auth/carddav-password", headers=auth).json()
        user = client.portal.call(system_db["users"].find_one, {"email": "anna@example.com"})

        assert len(issued["password"]) == 20
        assert issued["password"] not in str(user)
        assert client.get("/api/auth/me", headers=auth).json()["has_carddav_password"] is True


class TestLegacyAdmin:
    def test_single_user_settings_become_first_user_with_old_data(self, client, system_db, monkeypatch):
        monkeypatch.setattr(settings, "carddav_password", "old-phone-pass")
        # Данные однопользовательской версии лежат прямо в системной базе
        now = datetime.now(timezone.utc)
        client.portal.call(
            system_db["contacts"].insert_one,
            {"first_name": "Старый", "last_name": "", "created_at": now, "updated_at": now},
        )

        login = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
        auth = {"Authorization": f"Bearer {login.json()['access_token']}"}

        assert login.status_code == 200
        assert [c["first_name"] for c in client.get("/api/contacts/", headers=auth).json()] == ["Старый"]
        # Телефон, настроенный со старым CARDDAV_PASSWORD, продолжает работать
        dav = client.request("PROPFIND", BOOK, headers={**_basic("admin", "old-phone-pass"), "Depth": "1"})
        assert dav.status_code == 207
        assert dav.text.count(".vcf") == 1

    @pytest.mark.parametrize("password", [None, "admin", "short"])
    def test_weak_or_missing_legacy_password_creates_nobody(self, client, system_db, monkeypatch, password):
        monkeypatch.setattr(settings, "admin_password", password)

        login = client.post("/api/auth/login", data={"username": "admin", "password": password or "admin"})

        assert login.status_code == 401
        assert client.portal.call(system_db["users"].count_documents, {}) == 0

    def test_legacy_admin_created_even_after_someone_registered(self, client, system_db):
        _register(client, "first@example.com")

        login = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})

        assert login.status_code == 200

    def test_legacy_admin_is_created_once(self, client, system_db):
        for _ in range(3):
            client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})

        assert client.portal.call(system_db["users"].count_documents, {"email": "admin"}) == 1


class TestCallbacksWithoutJwt:
    @pytest.fixture
    def google_configured(self, monkeypatch):
        async def fake_exchange(code: str) -> dict:
            return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

        monkeypatch.setattr("app.routers.sync.google_configured", lambda: True)
        monkeypatch.setattr("app.routers.sync.google_authorize_url", lambda state: f"https://g/auth?state={state}")
        monkeypatch.setattr("app.routers.sync.google_exchange_code", fake_exchange)

    def test_oauth_callback_connects_account_of_state_owner(self, client, google_configured):
        anna = _register(client, "anna@example.com")
        boris = _register(client, "boris@example.com")
        state = client.post("/api/sync/connect/google", headers=anna).json()["state"]

        cb = client.get("/api/sync/callback/google", params={"code": "c", "state": state}, follow_redirects=False)

        assert "connected=google" in cb.headers["location"]
        assert len(client.get("/api/sync/connections", headers=anna).json()) == 1
        assert client.get("/api/sync/connections", headers=boris).json() == []

    def test_state_with_foreign_user_prefix_is_rejected(self, client, google_configured):
        anna = _register(client, "anna@example.com")
        boris = _register(client, "boris@example.com")
        boris_id = client.get("/api/auth/me", headers=boris).json()["id"]
        anna_state = client.post("/api/sync/connect/google", headers=anna).json()["state"]
        forged = f"{boris_id}.{anna_state.partition('.')[2]}"

        cb = client.get("/api/sync/callback/google", params={"code": "c", "state": forged}, follow_redirects=False)

        assert "invalid_state" in cb.headers["location"]
        assert client.get("/api/sync/connections", headers=boris).json() == []

    @pytest.mark.parametrize("client_state", ["64b000000000000000000000:abc", "garbage:", ""])
    def test_webhook_with_unknown_client_state_is_ignored(self, client, client_state):
        resp = client.post("/api/webhooks/microsoft", json={"value": [{"clientState": client_state}]})

        assert resp.status_code == 202


def test_backend_refuses_to_start_with_default_secret(monkeypatch):
    from app.config import INSECURE_SECRET_KEY, check_secrets

    for weak in (INSECURE_SECRET_KEY, "short-key"):
        monkeypatch.setattr(settings, "secret_key", weak)
        with pytest.raises(RuntimeError):
            check_secrets(settings)
