"""
Напоминания: /api/reminders и блок reminders в /api/home.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app
from app.services.reminders import next_due_date


class TestNextDueDate:
    def test_none_has_no_next(self):
        assert next_due_date(date(2026, 1, 1), "none") is None

    def test_weekly(self):
        assert next_due_date(date(2026, 12, 28), "weekly") == date(2027, 1, 4)

    def test_monthly_clamps_to_month_end(self):
        assert next_due_date(date(2026, 1, 31), "monthly") == date(2026, 2, 28)

    def test_monthly_wraps_year(self):
        assert next_due_date(date(2026, 12, 15), "monthly") == date(2027, 1, 15)

    def test_yearly_feb_29(self):
        assert next_due_date(date(2028, 2, 29), "yearly") == date(2029, 2, 28)


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["test_reminders"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def contact(client, auth) -> dict:
    return client.post("/api/contacts/", json={"first_name": "Анна", "last_name": "Орлова"}, headers=auth).json()


def _add(client, auth, title="Позвонить", due="2026-11-10", **extra) -> dict:
    resp = client.post("/api/reminders", json={"title": title, "due_date": due, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _titles(client, auth, **params) -> list[str]:
    return [r["title"] for r in client.get("/api/reminders", params=params, headers=auth).json()]


class TestCrud:
    def test_create_defaults(self, client, auth):
        r = _add(client, auth)

        assert r["repeat"] == "none"
        assert r["done_at"] is None
        assert r["contact_id"] is None
        assert r["note"] == ""

    def test_create_with_contact_returns_name(self, client, auth, contact):
        r = _add(client, auth, contact_id=contact["id"], due_time="09:30")

        assert r["contact_name"] == "Анна Орлова"
        assert r["due_time"] == "09:30"

    def test_unknown_contact_404(self, client, auth):
        resp = client.post(
            "/api/reminders",
            json={"title": "x", "due_date": "2026-11-10", "contact_id": "64b7f0f0f0f0f0f0f0f0f0f0"},
            headers=auth,
        )
        assert resp.status_code == 404

    @pytest.mark.parametrize("bad", [{"due_date": "10.11.2026"}, {"due_time": "25:00"}, {"title": " "}])
    def test_validation(self, client, auth, bad):
        body = {"title": "x", "due_date": "2026-11-10", **bad}
        assert client.post("/api/reminders", json=body, headers=auth).status_code == 422

    def test_patch(self, client, auth):
        r = _add(client, auth)
        resp = client.patch(f"/api/reminders/{r['id']}", json={"title": "Написать", "repeat": "weekly"}, headers=auth)

        assert resp.status_code == 200
        assert resp.json()["title"] == "Написать"
        assert resp.json()["repeat"] == "weekly"
        assert resp.json()["due_date"] == "2026-11-10"

    def test_patch_unknown_404(self, client, auth):
        assert client.patch("/api/reminders/nope", json={"title": "x"}, headers=auth).status_code == 404

    def test_delete(self, client, auth):
        r = _add(client, auth)
        assert client.delete(f"/api/reminders/{r['id']}", headers=auth).status_code == 204
        assert client.delete(f"/api/reminders/{r['id']}", headers=auth).status_code == 404

    def test_requires_auth(self, client):
        assert client.get("/api/reminders").status_code == 401


class TestList:
    def test_sorted_by_due_and_filters(self, client, auth, contact):
        _add(client, auth, "B", "2026-11-12")
        _add(client, auth, "A", "2026-11-10", contact_id=contact["id"])
        _add(client, auth, "C", "2026-11-20")

        assert _titles(client, auth) == ["A", "B", "C"]
        assert _titles(client, auth, **{"from": "2026-11-11", "to": "2026-11-15"}) == ["B"]
        assert _titles(client, auth, contact_id=contact["id"]) == ["A"]

    def test_status_filter(self, client, auth):
        a = _add(client, auth, "A", "2026-11-10")
        _add(client, auth, "B", "2026-11-11")
        client.post(f"/api/reminders/{a['id']}/done", headers=auth)

        assert _titles(client, auth, status="open") == ["B"]
        assert _titles(client, auth, status="done") == ["A"]
        assert _titles(client, auth, status="all") == ["A", "B"]


class TestDone:
    def test_done_sets_timestamp(self, client, auth):
        r = _add(client, auth)
        resp = client.post(f"/api/reminders/{r['id']}/done", headers=auth)

        assert resp.status_code == 200
        assert resp.json()["done_at"] is not None
        assert _titles(client, auth, status="all") == ["Позвонить"]

    def test_done_repeating_creates_next(self, client, auth, contact):
        r = _add(client, auth, due="2026-11-10", repeat="weekly", contact_id=contact["id"], due_time="08:00", note="n")
        client.post(f"/api/reminders/{r['id']}/done", headers=auth)

        open_ = client.get("/api/reminders", params={"status": "open"}, headers=auth).json()

        assert len(open_) == 1
        assert open_[0]["due_date"] == "2026-11-17"
        assert open_[0]["repeat"] == "weekly"
        assert open_[0]["contact_id"] == contact["id"]
        assert open_[0]["due_time"] == "08:00"
        assert open_[0]["note"] == "n"
        assert open_[0]["id"] != r["id"]

    def test_done_twice_does_not_duplicate(self, client, auth):
        r = _add(client, auth, repeat="monthly")
        client.post(f"/api/reminders/{r['id']}/done", headers=auth)
        client.post(f"/api/reminders/{r['id']}/done", headers=auth)

        assert len(_titles(client, auth, status="open")) == 1

    def test_done_unknown_404(self, client, auth):
        assert client.post("/api/reminders/nope/done", headers=auth).status_code == 404


class TestHome:
    def test_home_has_five_nearest_open(self, client, auth):
        for day in range(1, 8):
            _add(client, auth, f"R{day}", f"2026-11-{day + 9:02d}")
        first = client.get("/api/reminders", headers=auth).json()[0]
        client.post(f"/api/reminders/{first['id']}/done", headers=auth)

        home = client.get("/api/home", headers=auth).json()

        assert [r["title"] for r in home["reminders"]] == ["R2", "R3", "R4", "R5", "R6"]

    def test_home_empty(self, client, auth):
        assert client.get("/api/home", headers=auth).json()["reminders"] == []
