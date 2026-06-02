"""
Тесты аутентификации: login, токены, защищённые маршруты.

Используем FastAPI TestClient (sync), переопределяем зависимость get_db
через mongomock-motor чтобы контактные маршруты тоже работали без реального MongoDB.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.main import app
from app.db import get_db


# ---------------------------------------------------------------------------
# Фикстура: TestClient с подменённой БД
# ---------------------------------------------------------------------------

# Module-level singleton: все тесты одного модуля используют одну БД
_mock_client = AsyncMongoMockClient()
_mock_db = _mock_client["test_auth_crm"]


def override_get_db():
    """Возвращает shared in-memory MongoDB для тестов."""
    return _mock_db


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def get_token(client: TestClient, username: str = "admin", password: str = "admin") -> str:
    """Логин и получение токена."""
    resp = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Тесты auth
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_success(self, client):
        resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        resp = client.post(
            "/api/auth/login",
            data={"username": "admin", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_wrong_username(self, client):
        resp = client.post(
            "/api/auth/login",
            data={"username": "hacker", "password": "admin"},
        )
        assert resp.status_code == 401

    def test_login_json(self, client):
        """Логин через JSON-тело (/api/auth/login/json)."""
        resp = client.post(
            "/api/auth/login/json",
            json={"username": "admin", "password": "admin"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_json_wrong_password(self, client):
        resp = client.post(
            "/api/auth/login/json",
            json={"username": "admin", "password": "nope"},
        )
        assert resp.status_code == 401


class TestMe:
    def test_me_with_valid_token(self, client):
        token = get_token(client)
        resp = client.get("/api/auth/me", headers=auth_headers(token))
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"

    def test_me_without_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_me_with_bad_token(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert resp.status_code == 401


class TestProtectedContactRoutes:
    """Проверяем что /api/contacts/* требует токен."""

    def test_list_without_token_is_401(self, client):
        resp = client.get("/api/contacts/")
        assert resp.status_code == 401

    def test_create_without_token_is_401(self, client):
        resp = client.post("/api/contacts/", json={"first_name": "Test"})
        assert resp.status_code == 401

    def test_get_without_token_is_401(self, client):
        resp = client.get("/api/contacts/507f1f77bcf86cd799439011")
        assert resp.status_code == 401

    def test_patch_without_token_is_401(self, client):
        resp = client.patch("/api/contacts/507f1f77bcf86cd799439011", json={})
        assert resp.status_code == 401

    def test_delete_without_token_is_401(self, client):
        resp = client.delete("/api/contacts/507f1f77bcf86cd799439011")
        assert resp.status_code == 401

    def test_create_with_token(self, client):
        token = get_token(client)
        resp = client.post(
            "/api/contacts/",
            json={"first_name": "Тест", "last_name": "Токен"},
            headers=auth_headers(token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["first_name"] == "Тест"
        assert "id" in body

    def test_list_with_token(self, client):
        token = get_token(client)
        resp = client.get("/api/contacts/", headers=auth_headers(token))
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_nonexistent_returns_404(self, client):
        token = get_token(client)
        resp = client.get(
            "/api/contacts/507f1f77bcf86cd799439011",
            headers=auth_headers(token),
        )
        assert resp.status_code == 404

    def test_get_invalid_id_returns_404(self, client):
        token = get_token(client)
        resp = client.get("/api/contacts/not-a-valid-id", headers=auth_headers(token))
        assert resp.status_code == 404

    def test_full_crud_flow(self, client):
        """Создать → получить → обновить → удалить."""
        token = get_token(client)
        headers = auth_headers(token)

        # Create
        create_resp = client.post(
            "/api/contacts/",
            json={
                "first_name": "Алексей",
                "last_name": "Иванов",
                "phones": [{"value": "+79001112233", "label": "мобильный"}],
                "emails": [{"value": "alex@test.ru", "label": "рабочий"}],
                "company": "Тестовая компания",
                "category": "коллега",
                "priority": "medium",
            },
            headers=headers,
        )
        assert create_resp.status_code == 201
        contact_id = create_resp.json()["id"]

        # Get
        get_resp = client.get(f"/api/contacts/{contact_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["last_name"] == "Иванов"

        # Patch
        patch_resp = client.patch(
            f"/api/contacts/{contact_id}",
            json={"city": "Новосибирск", "priority": "high"},
            headers=headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["city"] == "Новосибирск"
        assert patch_resp.json()["priority"] == "high"
        assert patch_resp.json()["first_name"] == "Алексей"  # не изменилось

        # Delete
        del_resp = client.delete(f"/api/contacts/{contact_id}", headers=headers)
        assert del_resp.status_code == 204

        # After delete — 404
        get_after = client.get(f"/api/contacts/{contact_id}", headers=headers)
        assert get_after.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        token = get_token(client)
        resp = client.delete(
            "/api/contacts/507f1f77bcf86cd799439011",
            headers=auth_headers(token),
        )
        assert resp.status_code == 404


class TestHealthPublic:
    """Health-check должен быть публичным (без токена)."""

    def test_health_no_auth_required(self, client):
        resp = client.get("/api/health")
        # Статус 200, db может быть error (нет реального mongo), но ошибки 401 быть не должно
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
