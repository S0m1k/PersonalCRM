"""
Главная: ближайшие дни рождения и сводка /api/home.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app
from app.services.birthdays import upcoming_birthdays


def _people(*birthdays: str) -> list[dict]:
    return [{"id": str(i), "name": f"P{i}", "birthday": b} for i, b in enumerate(birthdays)]


class TestUpcomingBirthdays:
    def test_today_and_within_window_sorted(self):
        result = upcoming_birthdays(_people("1980-10-25", "1990-10-21", "1970-11-30"), date(2026, 10, 21), days=14)

        assert [(r["name"], r["days_until"]) for r in result] == [("P1", 0), ("P0", 4)]

    def test_wraps_over_new_year(self):
        result = upcoming_birthdays(_people("1985-01-02"), date(2026, 12, 30), days=7)

        assert result[0]["date"] == "2027-01-02"
        assert result[0]["days_until"] == 3
        assert result[0]["turns"] == 42

    def test_feb_29_in_non_leap_year_is_feb_28(self):
        result = upcoming_birthdays(_people("1992-02-29"), date(2027, 2, 20), days=14)

        assert result[0]["date"] == "2027-02-28"

    def test_unknown_birth_year_has_no_age(self):
        """Outlook/Apple хранят ДР без года как 1604/1900."""
        result = upcoming_birthdays(_people("1604-10-22"), date(2026, 10, 21), days=7)

        assert result[0]["turns"] is None

    def test_missing_or_broken_birthdays_are_skipped(self):
        people = [{"id": "1", "name": "A", "birthday": None}, {"id": "2", "name": "B", "birthday": "кривая"}]

        assert upcoming_birthdays(people, date(2026, 10, 21), days=30) == []


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["test_home"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


class TestHomeApi:
    def test_summary(self, client, auth):
        today = date.today()
        petr = client.post(
            "/api/contacts/",
            json={"first_name": "Пётр", "birthday": today.replace(year=1980).isoformat()},
            headers=auth,
        ).json()
        client.post("/api/contacts/", json={"first_name": "Марина"}, headers=auth)
        client.post("/api/questions", json={"contact_id": petr["id"], "text": "Как дела?"}, headers=auth)

        home = client.get("/api/home", headers=auth).json()

        assert home["stats"] == {"contacts": 2, "open_questions": 1}
        assert [b["name"] for b in home["birthdays"]] == ["Пётр"]
        assert home["birthdays"][0]["days_until"] == 0
        assert [r["name"] for r in home["recent"]] == ["Марина", "Пётр"]
        assert home["open_questions"][0]["contact_name"] == "Пётр"

    def test_client_local_date_is_used_for_birthdays(self, client, auth):
        """Сервер может жить в UTC, а у пользователя уже следующий день."""
        far_from_now = date.today() + timedelta(days=120)
        client.post(
            "/api/contacts/",
            json={"first_name": "Анна", "birthday": far_from_now.replace(year=1985).isoformat()},
            headers=auth,
        )

        home = client.get("/api/home", params={"today": far_from_now.isoformat()}, headers=auth).json()

        assert home["birthdays"][0]["days_until"] == 0

    def test_sprint11_blocks(self, client, auth):
        quiet = client.post(
            "/api/contacts/", json={"first_name": "Тихий", "keep_in_touch": {"frequency_days": 3}}, headers=auth
        ).json()
        talked = client.post("/api/contacts/", json={"first_name": "Болтун", "tags": ["друг", "бег"]}, headers=auth).json()
        client.post("/api/groups", json={"name": "Семья"}, headers=auth)
        client.post("/api/interactions", json={"contact_ids": [talked["id"]], "title": "Кофе"}, headers=auth)
        far = (date.today() + timedelta(days=60)).isoformat()

        home = client.get("/api/home", params={"today": far}, headers=auth).json()

        assert [i["contact_id"] for i in home["keep_in_touch_overdue"]] == [quiet["id"]]
        assert home["keep_in_touch_overdue"][0]["days_overdue"] > 0
        assert [(i["title"], i["contacts"]) for i in home["recent_interactions"]] == [
            ("Кофе", [{"id": talked["id"], "name": "Болтун"}])
        ]
        assert home["counts"] == {"groups": 1, "tags": 2}
        # прежние поля на месте
        assert home["stats"] == {"contacts": 2, "open_questions": 0}

    def test_keep_in_touch_overdue_is_capped_at_five(self, client, auth):
        for i in range(7):
            client.post("/api/contacts/", json={"first_name": f"П{i}", "keep_in_touch": {"frequency_days": 1}}, headers=auth)
        far = (date.today() + timedelta(days=30)).isoformat()

        home = client.get("/api/home", params={"today": far}, headers=auth).json()

        assert len(home["keep_in_touch_overdue"]) == 5

    def test_recent_interactions_are_limited_to_five_newest_first(self, client, auth):
        c = client.post("/api/contacts/", json={"first_name": "А"}, headers=auth).json()
        for i in range(7):
            client.post("/api/interactions", json={"contact_ids": [c["id"]], "title": f"n{i}"}, headers=auth)

        home = client.get("/api/home", headers=auth).json()

        assert [i["title"] for i in home["recent_interactions"]] == ["n6", "n5", "n4", "n3", "n2"]

    def test_invalid_today_is_422(self, client, auth):
        assert client.get("/api/home", params={"today": "вчера"}, headers=auth).status_code == 422

    def test_requires_auth(self, client):
        assert client.get("/api/home").status_code == 401
