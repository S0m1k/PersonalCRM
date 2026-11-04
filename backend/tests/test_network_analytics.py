"""
Вселенная (/api/network/universe) и инсайты (/api/network/insights).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.insights import build_insights
from app.services.universe import build_universe, tokenize

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)

DEVS = [("Аня", "Python разработчик", "Яндекс"), ("Боря", "Backend разработчик Python", "Яндекс"), ("Вика", "Python инженер", "Яндекс")]
DOCTORS = [("Глеб", "Хирург", "Клиника Здоровье"), ("Дина", "Врач хирург", "Клиника Здоровье"), ("Егор", "Хирург врач", "Клиника")]
CHEFS = [("Жанна", "Шеф повар", "Ресторан Белуга"), ("Зина", "Повар ресторана", "Ресторан Белуга")]


def make_contact(client, auth, name, position="", company="", **extra) -> dict:
    resp = client.post(
        "/api/contacts/", json={"first_name": name, "position": position, "company": company, **extra}, headers=auth
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def docs(rows):
    return [{"_id": f"id-{i:02d}-{n}", "first_name": n, "position": p, "company": c} for i, (n, p, c) in enumerate(rows)]


class TestUniverseUnits:
    def test_tokenize_drops_short_stop_and_digits(self):
        assert tokenize("The ООО «Рога» и 123 копыта, IT") == ["рога", "копыта"]

    def test_not_ready_below_threshold(self):
        result = build_universe(docs(DEVS))

        assert result.ready is False and result.profiled == 3 and result.clusters == []

    def test_contacts_without_profile_do_not_count(self):
        rows = DEVS + DOCTORS + CHEFS
        empty = [{"_id": f"empty-{i}", "first_name": "X"} for i in range(5)]

        result = build_universe(docs(rows) + empty)

        assert result.profiled == len(rows)
        assert all(not cid.startswith("empty") for cid in result.positions)

    def test_clusters_by_similarity_and_labels(self):
        result = build_universe(docs(DEVS + DOCTORS + CHEFS))

        assert result.ready
        by_label = {c.label: {i.split("-")[2] for i in c.contact_ids} for c in result.clusters}
        groups = [set(m) for m in by_label.values()]
        assert {"Аня", "Боря", "Вика"} in groups
        assert {"Глеб", "Дина", "Егор"} in groups
        assert {"Жанна", "Зина"} in groups
        assert any("python" in label.lower() or "яндекс" in label.lower() for label in by_label)

    def test_every_profiled_contact_is_placed_exactly_once(self):
        result = build_universe(docs(DEVS + DOCTORS + CHEFS))

        placed = [cid for c in result.clusters for cid in c.contact_ids]
        assert sorted(placed) == sorted(result.positions) and len(placed) == len(set(placed)) == 8

    def test_deterministic(self):
        rows = DEVS + DOCTORS + CHEFS

        assert build_universe(docs(rows)).model_dump() == build_universe(docs(rows)).model_dump()


class TestUniverseApi:
    def test_not_ready(self, crm_client, crm_auth):
        make_contact(crm_client, crm_auth, "Аня", "Python разработчик")

        body = crm_client.get("/api/network/universe", headers=crm_auth).json()

        assert body["ready"] is False and body["required"] == 8 and body["clusters"] == []

    def test_ready(self, crm_client, crm_auth):
        ids = {}
        for name, position, company in DEVS + DOCTORS + CHEFS:
            ids[name] = make_contact(crm_client, crm_auth, name, position, company)["id"]

        body = crm_client.get("/api/network/universe", headers=crm_auth).json()

        assert body["ready"] is True
        assert set(body["positions"]) == set(ids.values())
        assert all({"x", "y"} == set(p) for p in body["positions"].values())
        assert sum(len(c["contact_ids"]) for c in body["clusters"]) == 8

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/network/universe").status_code == 401


def contact_doc(created, **extra):
    return {"created_at": created, **extra}


class TestInsightsUnits:
    def test_recency_buckets(self):
        days = lambda n: NOW - timedelta(days=n)  # noqa: E731
        rows = [
            {"last_interaction_at": days(5)},
            {"last_interaction_at": days(45)},
            {"last_interaction_at": days(120)},
            {"last_interaction_at": days(300)},
            {"last_interaction_at": days(800)},
            {},
            {"last_interaction_at": None},
        ]

        series = {s.label: s.count for s in build_insights(rows, {}, NOW).by_recency}

        assert series == {
            "Меньше месяца": 1, "1–3 месяца": 1, "3–6 месяцев": 1, "6–12 месяцев": 1, "Больше года": 1, "Никогда": 2,
        }

    def test_naive_datetimes_are_treated_as_utc(self):
        series = build_insights([{"last_interaction_at": datetime(2026, 11, 1)}], {}, NOW).by_recency

        assert series[0].count == 1

    def test_top_lists_case_insensitive_and_limited(self):
        rows = [{"company": "Acme"}, {"company": " acme "}, {"company": "Beta"}] + [{"company": f"C{i}"} for i in range(12)]

        result = build_insights(rows, {}, NOW)

        assert result.by_company[0].model_dump() == {"label": "Acme", "count": 2}
        assert len(result.by_company) == 10

    def test_tags_and_groups(self):
        rows = [
            {"tags": ["друг", "Друг", "ИТ"], "group_ids": ["g1"]},
            {"tags": ["друг"], "group_ids": ["g1", "gone"]},
        ]

        result = build_insights(rows, {"g1": "Семья"}, NOW)

        assert [(s.label, s.count) for s in result.by_tag] == [("друг", 2), ("ИТ", 1)]
        assert [(s.label, s.count) for s in result.by_group] == [("Семья", 2)]

    def test_frequency_buckets(self):
        rows = [
            {"keep_in_touch": {"frequency_days": 7}},
            {"keep_in_touch": {"frequency_days": 30}},
            {"keep_in_touch": {"frequency_days": 90}},
            {"keep_in_touch": {"frequency_days": 700}},
            {"keep_in_touch": {"frequency_days": None}},
            {},
        ]

        series = {s.label: s.count for s in build_insights(rows, {}, NOW).by_frequency}

        assert series["Раз в неделю и чаще"] == 1 and series["Раз в месяц"] == 1 and series["Раз в квартал"] == 1
        assert series["Реже раза в год"] == 1 and series["Не задана"] == 2

    def test_growth_is_cumulative_and_fills_empty_months(self):
        rows = [
            contact_doc(datetime(2026, 8, 3, tzinfo=timezone.utc)),
            contact_doc(datetime(2026, 8, 20, tzinfo=timezone.utc)),
            contact_doc(datetime(2026, 10, 1, tzinfo=timezone.utc)),
        ]

        growth = build_insights(rows, {}, NOW).growth

        assert [(p.month, p.added, p.total) for p in growth] == [
            ("2026-08", 2, 2), ("2026-09", 0, 2), ("2026-10", 1, 3), ("2026-11", 0, 3),
        ]

    def test_enough_threshold(self):
        assert build_insights([{}] * 19, {}, NOW).enough is False
        assert build_insights([{}] * 20, {}, NOW).enough is True

    def test_empty(self):
        result = build_insights([], {}, NOW)

        assert result.total == 0 and result.growth == [] and result.by_company == []
        assert len(result.by_recency) == 6


class TestInsightsApi:
    def test_returns_all_series(self, crm_client, crm_auth):
        group = crm_client.post("/api/groups", json={"name": "Семья"}, headers=crm_auth).json()
        make_contact(crm_client, crm_auth, "Аня", company="ACME", city="Москва", tags=["друг"], group_ids=[group["id"]])
        make_contact(crm_client, crm_auth, "Боря", company="acme", city="Казань")

        body = crm_client.get("/api/network/insights", headers=crm_auth).json()

        assert body["total"] == 2 and body["enough"] is False and body["required"] == 20
        assert body["by_company"] == [{"label": "ACME", "count": 2}]
        assert {s["label"] for s in body["by_city"]} == {"Москва", "Казань"}
        assert body["by_tag"] == [{"label": "друг", "count": 1}]
        assert body["by_group"] == [{"label": "Семья", "count": 1}]
        assert sum(s["count"] for s in body["by_recency"]) == 2
        assert sum(s["count"] for s in body["by_frequency"]) == 2
        assert body["growth"][-1]["total"] == 2

    def test_empty_database(self, crm_client, crm_auth):
        body = crm_client.get("/api/network/insights", headers=crm_auth).json()

        assert body["total"] == 0 and body["growth"] == []

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/network/insights").status_code == 401
