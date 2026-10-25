"""
Тесты OAuth callback: проверка state (защита от CSRF / подмены аккаунта)
и редирект обратно во фронтенд, а не на относительный путь бэкенда.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.config import settings
from app.db import get_db
from app.main import app

_mock_db = AsyncMongoMockClient()["test_oauth_state"]


@pytest.fixture(scope="module")
def client():
    app.dependency_overrides[get_db] = lambda: _mock_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def auth(client):
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def providers_configured(monkeypatch):
    """Делаем вид, что ключи Microsoft и Google заданы, а обмен кода — успешен."""

    async def fake_exchange(code: str) -> dict:
        return {"access_token": "a", "refresh_token": "r", "expires_in": 3600}

    monkeypatch.setattr("app.routers.sync.ms_configured", lambda: True)
    monkeypatch.setattr("app.routers.sync.google_configured", lambda: True)
    monkeypatch.setattr("app.routers.sync.ms_authorize_url", lambda state: f"https://ms/auth?state={state}")
    monkeypatch.setattr("app.routers.sync.google_authorize_url", lambda state: f"https://g/auth?state={state}")
    monkeypatch.setattr("app.routers.sync.ms_exchange_code", fake_exchange)
    monkeypatch.setattr("app.routers.sync.google_exchange_code", fake_exchange)


def _connections(client, auth, provider: str) -> int:
    conns = client.get("/api/sync/connections", headers=auth).json()
    return len([c for c in conns if c["provider"] == provider])


@pytest.mark.parametrize("provider", ["microsoft", "google"])
class TestOAuthState:
    def test_callback_without_state_is_rejected(self, client, auth, providers_configured, provider):
        before = _connections(client, auth, provider)

        cb = client.get(f"/api/sync/callback/{provider}", params={"code": "c"}, follow_redirects=False)

        assert cb.status_code == 302
        assert "error=invalid_state" in cb.headers["location"]
        assert _connections(client, auth, provider) == before

    def test_callback_with_unknown_state_is_rejected(self, client, auth, providers_configured, provider):
        before = _connections(client, auth, provider)

        cb = client.get(
            f"/api/sync/callback/{provider}",
            params={"code": "c", "state": "forged-state"},
            follow_redirects=False,
        )

        assert "error=invalid_state" in cb.headers["location"]
        assert _connections(client, auth, provider) == before

    def test_issued_state_is_accepted_once(self, client, auth, providers_configured, provider):
        state = client.post(f"/api/sync/connect/{provider}", headers=auth).json()["state"]
        before = _connections(client, auth, provider)

        first = client.get(
            f"/api/sync/callback/{provider}", params={"code": "c", "state": state}, follow_redirects=False
        )
        replay = client.get(
            f"/api/sync/callback/{provider}", params={"code": "c", "state": state}, follow_redirects=False
        )

        assert f"connected={provider}" in first.headers["location"]
        assert "error=invalid_state" in replay.headers["location"]
        assert _connections(client, auth, provider) == before + 1

    def test_state_of_other_provider_is_rejected(self, client, auth, providers_configured, provider):
        other = "google" if provider == "microsoft" else "microsoft"
        state = client.post(f"/api/sync/connect/{other}", headers=auth).json()["state"]

        cb = client.get(
            f"/api/sync/callback/{provider}", params={"code": "c", "state": state}, follow_redirects=False
        )

        assert "error=invalid_state" in cb.headers["location"]


class TestRedirectTarget:
    def test_redirects_to_frontend_sync_page(self, client, auth, providers_configured):
        state = client.post("/api/sync/connect/google", headers=auth).json()["state"]

        cb = client.get(
            "/api/sync/callback/google", params={"code": "c", "state": state}, follow_redirects=False
        )

        assert cb.headers["location"].startswith(f"{settings.frontend_url.rstrip('/')}/sync?")

    def test_provider_error_description_is_url_encoded(self, client, providers_configured):
        cb = client.get(
            "/api/sync/callback/microsoft",
            params={"error": "access_denied", "error_description": "user said no & left"},
            follow_redirects=False,
        )

        location = cb.headers["location"]
        assert "error=access_denied" in location
        assert "user said no & left" not in location
        assert "user+said+no+%26+left" in location
