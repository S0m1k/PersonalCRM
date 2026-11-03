"""
Keep in touch: корзины (чистая логика), GET /api/keep-in-touch, snooze, touched.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.services.keep_in_touch import bucketize, build_item

TODAY = date(2026, 11, 10)
NOW = datetime.now(timezone.utc)


def doc(name="Анна", frequency=30, created="2026-01-01", snoozed=None, **extra) -> dict:
    created_dt = datetime.fromisoformat(created).replace(tzinfo=timezone.utc)
    return {
        "_id": ObjectId(),
        "first_name": name,
        "created_at": created_dt,
        "keep_in_touch": {"frequency_days": frequency, "snoozed_until": snoozed},
        **extra,
    }


def at(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=timezone.utc)


class TestBuildItem:
    def test_due_date_is_last_interaction_plus_frequency(self):
        item = build_item(doc(frequency=14), at("2026-10-20"), TODAY)

        assert item.due_date == date(2026, 11, 3)
        assert (item.days_overdue, item.days_until) == (7, 0)

    def test_without_interactions_creation_date_is_the_anchor(self):
        item = build_item(doc(frequency=30, created="2026-10-25"), None, TODAY)

        assert item.due_date == date(2026, 11, 24)
        assert (item.days_overdue, item.days_until) == (0, 14)
        assert item.last_interaction_at is None

    def test_no_frequency_means_no_item(self):
        assert build_item(doc(frequency=None), None, TODAY) is None
        assert build_item({"_id": ObjectId(), "first_name": "Старый"}, None, TODAY) is None

    def test_naive_datetimes_from_mongo_are_ok(self):
        item = build_item(doc(frequency=10), datetime(2026, 11, 1, 12, 0), TODAY)

        assert item.due_date == date(2026, 11, 11) and item.last_interaction_at.tzinfo is not None


class TestBucketize:
    def test_buckets_and_ordering(self):
        docs = [
            doc("Давно", 30, created="2026-01-01"),  # просрочен сильно
            doc("Вчера", 10, created="2026-10-01"),  # срок 10 окт — просрочен на 31, но есть общение ниже
            doc("СкороА", 7),
            doc("Позже", 90),
            doc("Отложен", 30, snoozed="2026-11-20"),
            doc("Без частоты", None),
        ]
        last = {
            str(docs[1]["_id"]): at("2026-10-30"),  # срок 9 ноя → просрочен на 1 день
            str(docs[2]["_id"]): at("2026-11-08"),  # срок 15 ноя → due_soon (5 дней)
            str(docs[3]["_id"]): at("2026-11-09"),  # срок в феврале → upcoming
        }

        buckets = bucketize(docs, last, TODAY)

        assert [i.name for i in buckets.overdue] == ["Давно", "Вчера"]
        assert [i.name for i in buckets.due_soon] == ["СкороА"]
        assert [i.name for i in buckets.upcoming] == ["Позже"]
        assert [i.name for i in buckets.snoozed] == ["Отложен"]

    def test_due_today_is_due_soon_not_overdue(self):
        d = doc(frequency=10)
        buckets = bucketize([d], {str(d["_id"]): at("2026-10-31")}, TODAY)

        assert [i.days_overdue for i in buckets.due_soon] == [0] and buckets.overdue == []

    def test_due_in_exactly_seven_days_is_due_soon_and_eight_is_upcoming(self):
        seven, eight = doc("Семь", 10), doc("Восемь", 10)
        last = {str(seven["_id"]): at("2026-11-07"), str(eight["_id"]): at("2026-11-08")}

        buckets = bucketize([seven, eight], last, TODAY)

        assert [i.name for i in buckets.due_soon] == ["Семь"]
        assert [i.name for i in buckets.upcoming] == ["Восемь"]

    def test_snooze_through_its_last_day_then_expires(self):
        d = doc("Отложен", 30, snoozed="2026-11-10")  # до сегодняшнего дня включительно
        assert len(bucketize([d], {}, TODAY).snoozed) == 1
        assert len(bucketize([d], {}, date(2026, 11, 11)).snoozed) == 0

    def test_snoozed_overdue_is_only_in_snoozed(self):
        d = doc("Давно", 30, created="2025-01-01", snoozed="2026-12-01")
        buckets = bucketize([d], {}, TODAY)

        assert len(buckets.snoozed) == 1 and buckets.overdue == []

    def test_stored_last_interaction_is_used_when_no_fresh_value(self):
        d = doc(frequency=5, last_interaction_at=at("2026-11-09"))

        buckets = bucketize([d], {}, TODAY)

        assert buckets.due_soon[0].due_date == date(2026, 11, 14)

    def test_overdue_ties_prefer_more_important(self):
        a, b = doc("А", 10, importance=1), doc("Б", 10, importance=5)
        buckets = bucketize([a, b], {}, TODAY)

        assert [i.name for i in buckets.overdue] == ["Б", "А"]

    def test_broken_snooze_value_is_ignored(self):
        d = doc("Анна", 10, snoozed="не дата")

        assert len(bucketize([d], {}, TODAY).overdue) == 1


def make_contact(client, auth, name="Анна", **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestApi:
    def test_endpoint_returns_buckets_with_fresh_last_interaction(self, crm_client, crm_auth):
        today = datetime.now(timezone.utc).date()  # давность считается от даты в UTC
        quiet = make_contact(crm_client, crm_auth, "Тихий", keep_in_touch={"frequency_days": 7})
        recent = make_contact(crm_client, crm_auth, "Недавний", keep_in_touch={"frequency_days": 30})
        make_contact(crm_client, crm_auth, "Без частоты")
        crm_client.post("/api/interactions", json={"contact_ids": [recent["id"]]}, headers=crm_auth)

        resp = crm_client.get("/api/keep-in-touch", params={"today": (today + timedelta(days=10)).isoformat()}, headers=crm_auth)

        assert resp.status_code == 200
        body = resp.json()
        assert set(body) == {"overdue", "due_soon", "upcoming", "snoozed"}
        assert [i["contact_id"] for i in body["overdue"]] == [quiet["id"]]
        assert body["overdue"][0]["days_overdue"] == 3
        assert [i["name"] for i in body["upcoming"]] == ["Недавний"]
        item = body["upcoming"][0]
        assert item["last_interaction_at"] is not None
        assert item["due_date"] == (today + timedelta(days=30)).isoformat()
        assert item["frequency_days"] == 30

    def test_snooze_moves_contact_to_snoozed(self, crm_client, crm_auth):
        c = make_contact(crm_client, crm_auth, keep_in_touch={"frequency_days": 1})
        far = (date.today() + timedelta(days=30)).isoformat()

        resp = crm_client.post(f"/api/contacts/{c['id']}/snooze", json={"days": 14, "today": far}, headers=crm_auth)

        assert resp.status_code == 200
        until = (date.fromisoformat(far) + timedelta(days=14)).isoformat()
        assert resp.json()["keep_in_touch"] == {"frequency_days": 1, "snoozed_until": until}
        body = crm_client.get("/api/keep-in-touch", params={"today": far}, headers=crm_auth).json()
        assert [i["contact_id"] for i in body["snoozed"]] == [c["id"]] and body["overdue"] == []
        assert body["snoozed"][0]["snoozed_until"] == until

    def test_snooze_does_not_bump_updated_at(self, crm_client, crm_auth):
        c = make_contact(crm_client, crm_auth, keep_in_touch={"frequency_days": 5})

        resp = crm_client.post(f"/api/contacts/{c['id']}/snooze", json={"days": 3}, headers=crm_auth)

        before = datetime.fromisoformat(c["updated_at"])
        after = datetime.fromisoformat(resp.json()["updated_at"])
        assert abs(after - before) < timedelta(milliseconds=2)  # Mongo хранит миллисекунды

    def test_snooze_validates_days_and_contact(self, crm_client, crm_auth):
        c = make_contact(crm_client, crm_auth)
        for days in (0, 366, -1):
            assert crm_client.post(f"/api/contacts/{c['id']}/snooze", json={"days": days}, headers=crm_auth).status_code == 422
        assert crm_client.post("/api/contacts/64b000000000000000000000/snooze", json={"days": 3}, headers=crm_auth).status_code == 404
        assert crm_client.post("/api/contacts/плохой/snooze", json={"days": 3}, headers=crm_auth).status_code == 404

    def test_touched_logs_interaction_and_clears_snooze(self, crm_client, crm_auth):
        c = make_contact(crm_client, crm_auth, keep_in_touch={"frequency_days": 30})
        crm_client.post(f"/api/contacts/{c['id']}/snooze", json={"days": 10}, headers=crm_auth)

        resp = crm_client.post(f"/api/contacts/{c['id']}/touched", headers=crm_auth)

        assert resp.status_code == 201
        body = resp.json()
        assert (body["kind"], body["title"], body["contact_ids"]) == ("note", "Связались", [c["id"]])
        fetched = crm_client.get(f"/api/contacts/{c['id']}", headers=crm_auth).json()
        assert fetched["keep_in_touch"]["snoozed_until"] is None
        assert fetched["last_interaction_at"] is not None

    def test_touched_with_custom_kind(self, crm_client, crm_auth):
        c = make_contact(crm_client, crm_auth)

        resp = crm_client.post(
            f"/api/contacts/{c['id']}/touched", json={"kind": "call", "title": "Созвонились"}, headers=crm_auth
        )

        assert (resp.json()["kind"], resp.json()["title"]) == ("call", "Созвонились")
        assert crm_client.post(f"/api/contacts/{c['id']}/touched", json={"kind": "телепатия"}, headers=crm_auth).status_code == 422

    def test_touched_unknown_contact_is_404(self, crm_client, crm_auth):
        assert crm_client.post("/api/contacts/64b000000000000000000000/touched", headers=crm_auth).status_code == 404

    def test_after_touched_contact_is_no_longer_overdue(self, crm_client, crm_auth):
        c = make_contact(crm_client, crm_auth, keep_in_touch={"frequency_days": 7})
        crm_client.post(f"/api/contacts/{c['id']}/touched", headers=crm_auth)

        body = crm_client.get("/api/keep-in-touch", headers=crm_auth).json()

        assert body["overdue"] == []
        assert [i["contact_id"] for i in body["upcoming"] + body["due_soon"]] == [c["id"]]

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/keep-in-touch").status_code == 401
        assert crm_client.post("/api/contacts/x/snooze", json={"days": 1}).status_code == 401


@pytest.mark.parametrize("bad", ["вчера", "2026-13-40"])
def test_today_param_is_validated(crm_client, crm_auth, bad):
    assert crm_client.get("/api/keep-in-touch", params={"today": bad}, headers=crm_auth).status_code == 422
