"""
Геокодирование: /api/geo/search и /api/geo/geocode-contacts. Запросы к Nominatim подменены.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.routers import geo as geo_router
from app.services import geocode

PARIS = {"lat": "48.85", "lon": "2.35", "display_name": "Paris, France"}


@pytest.fixture
def nominatim(monkeypatch):
    """Подменяет сетевой вызов; calls — список запрошенных строк."""
    calls: list[str] = []
    answers: dict[str, list[dict]] = {"paris": [PARIS]}

    async def fake_fetch(query: str, limit: int) -> list[dict]:
        calls.append(query)
        if query == "boom":
            raise httpx.ConnectError("нет сети")
        return answers.get(query, [])

    monkeypatch.setattr(geocode, "fetch_nominatim", fake_fetch)
    monkeypatch.setattr(geocode, "min_interval_s", 0.0)
    monkeypatch.setattr(geo_router, "_running", set())
    return calls, answers


def make_contact(client, auth, name, **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestUnits:
    def test_normalize_query(self):
        assert geocode.normalize_query("  Paris,   FRANCE ") == "paris, france"

    def test_user_agent_has_no_email(self):
        assert geocode.USER_AGENT == "PersonalCRM self-hosted"
        assert "@" not in geocode.USER_AGENT

    def test_parse_skips_broken_items(self):
        places = geocode._parse([PARIS, {"lat": "x", "lon": "1"}, {"display_name": "?"}])

        assert [(p.lat, p.lng) for p in places] == [(48.85, 2.35)]


class TestSearch:
    def test_returns_places_and_caches(self, crm_client, crm_auth, nominatim):
        calls, _ = nominatim

        first = crm_client.get("/api/geo/search", params={"q": "Paris"}, headers=crm_auth)
        second = crm_client.get("/api/geo/search", params={"q": "  paris "}, headers=crm_auth)

        assert first.status_code == 200
        assert first.json() == [{"lat": 48.85, "lng": 2.35, "label": "Paris, France"}]
        assert second.json() == first.json()
        assert calls == ["paris"]  # второй раз — из кэша

    def test_cache_holds_only_place_text(self, crm_client, crm_auth, nominatim):
        crm_client.get("/api/geo/search", params={"q": "Paris"}, headers=crm_auth)

        from app.db import get_db
        from app.main import app

        system_db = app.dependency_overrides[get_db]()
        doc = crm_client.portal.call(system_db[geocode.CACHE_COLLECTION].find_one, {"_id": "paris"})

        assert set(doc) == {"_id", "places"}

    def test_requires_auth(self, crm_client, nominatim):
        assert crm_client.get("/api/geo/search", params={"q": "Paris"}).status_code == 401

    def test_validates_query(self, crm_client, crm_auth, nominatim):
        assert crm_client.get("/api/geo/search", params={"q": "a"}, headers=crm_auth).status_code == 422

    def test_upstream_failure_is_502_and_not_cached(self, crm_client, crm_auth, nominatim):
        calls, _ = nominatim

        assert crm_client.get("/api/geo/search", params={"q": "boom"}, headers=crm_auth).status_code == 502
        assert crm_client.get("/api/geo/search", params={"q": "boom"}, headers=crm_auth).status_code == 502
        assert calls == ["boom", "boom"]

    def test_disabled(self, crm_client, crm_auth, nominatim, monkeypatch):
        monkeypatch.setattr(settings, "geocoding_enabled", False)

        assert crm_client.get("/api/geo/search", params={"q": "Paris"}, headers=crm_auth).status_code == 503
        assert crm_client.post("/api/geo/geocode-contacts", headers=crm_auth).status_code == 503


class TestThrottle:
    def test_waits_between_requests(self, monkeypatch):
        import asyncio

        slept: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)

        monkeypatch.setattr(geocode.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(geocode, "min_interval_s", 1.0)
        monkeypatch.setattr(geocode, "_last_request_at", geocode.time.monotonic())

        asyncio.run(geocode._wait_turn())

        assert len(slept) == 1 and 0 < slept[0] <= 1.0


class TestGeocodeContacts:
    def test_fills_only_missing_locations(self, crm_client, crm_auth, nominatim):
        calls, answers = nominatim
        answers["paris"] = [PARIS]
        answers["berlin, mitte"] = [{"lat": "52.5", "lon": "13.4", "display_name": "Mitte, Berlin"}]
        by_city = make_contact(crm_client, crm_auth, "Анна", city="Paris")
        by_address = make_contact(crm_client, crm_auth, "Борис", address="Berlin, Mitte", city="Paris")
        manual = make_contact(
            crm_client, crm_auth, "Вера", city="Paris", location={"lat": 1.0, "lng": 2.0, "label": "Дача"}
        )
        nothing = make_contact(crm_client, crm_auth, "Глеб")
        lost = make_contact(crm_client, crm_auth, "Дина", city="Atlantis")

        resp = crm_client.post("/api/geo/geocode-contacts", headers=crm_auth)

        assert resp.status_code == 202
        assert resp.json() == {"queued": 3, "already_running": False}
        get = lambda c: crm_client.get(f"/api/contacts/{c['id']}", headers=crm_auth).json()  # noqa: E731
        assert get(by_city)["location"] == {"lat": 48.85, "lng": 2.35, "label": "Paris, France"}
        assert get(by_address)["location"]["label"] == "Mitte, Berlin"  # адрес важнее города
        assert get(manual)["location"] == {"lat": 1.0, "lng": 2.0, "label": "Дача"}  # вручную — не трогаем
        assert get(nothing)["location"] is None
        assert get(lost)["location"] is None
        assert "boom" not in calls

    def test_nothing_to_do(self, crm_client, crm_auth, nominatim):
        make_contact(crm_client, crm_auth, "Анна")

        resp = crm_client.post("/api/geo/geocode-contacts", headers=crm_auth)

        assert resp.json() == {"queued": 0, "already_running": False}
        assert crm_client.get("/api/geo/missing", headers=crm_auth).json() == {"missing": 0}

    def test_network_error_does_not_break_the_batch(self, crm_client, crm_auth, nominatim):
        make_contact(crm_client, crm_auth, "Анна", city="boom")
        ok = make_contact(crm_client, crm_auth, "Борис", city="Paris")

        crm_client.post("/api/geo/geocode-contacts", headers=crm_auth)

        assert crm_client.get(f"/api/contacts/{ok['id']}", headers=crm_auth).json()["location"]["lat"] == 48.85
        assert crm_client.get("/api/geo/missing", headers=crm_auth).json() == {"missing": 1}
