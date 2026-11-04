"""
Фильтры списка контактов для таблицы «Все контакты»: частота, приоритет, источник, давность связи,
день рождения, место; счётчик /api/contacts/count и места /api/places.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def make(client, auth, name, **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def names(client, auth, **params) -> list[str]:
    resp = client.get("/api/contacts/", params={"sort": "name", **params}, headers=auth)
    assert resp.status_code == 200, resp.text
    return [c["first_name"] for c in resp.json()]


def interact(client, auth, contact_id, days_ago) -> None:
    when = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    resp = client.post("/api/interactions", json={"contact_ids": [contact_id], "occurred_at": when}, headers=auth)
    assert resp.status_code == 201, resp.text


class TestListFilters:
    def test_has_frequency(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", keep_in_touch={"frequency_days": 30})
        make(crm_client, crm_auth, "Борис")

        assert names(crm_client, crm_auth, has_frequency="true") == ["Анна"]
        assert names(crm_client, crm_auth, has_frequency="false") == ["Борис"]

    def test_has_priority(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", priority="top")
        make(crm_client, crm_auth, "Борис")
        make(crm_client, crm_auth, "Вера", priority="none")

        assert names(crm_client, crm_auth, has_priority="true") == ["Анна", "Вера"]
        assert names(crm_client, crm_auth, has_priority="false") == ["Борис"]

    def test_source(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", source="google")
        make(crm_client, crm_auth, "Борис")

        assert names(crm_client, crm_auth, source="google") == ["Анна"]
        assert names(crm_client, crm_auth, source="manual") == ["Борис"]

    def test_inactive_days_includes_never(self, crm_client, crm_auth):
        old = make(crm_client, crm_auth, "Анна")
        fresh = make(crm_client, crm_auth, "Борис")
        make(crm_client, crm_auth, "Вера")
        interact(crm_client, crm_auth, old["id"], 100)
        interact(crm_client, crm_auth, fresh["id"], 2)

        assert names(crm_client, crm_auth, inactive_days=30) == ["Анна", "Вера"]

    def test_has_birthday(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", birthday="1990-05-01")
        make(crm_client, crm_auth, "Борис")

        assert names(crm_client, crm_auth, has_birthday="true") == ["Анна"]

    def test_has_place(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", city="Казань")
        make(crm_client, crm_auth, "Борис", address="Тверская 1")
        make(crm_client, crm_auth, "Вера", location={"lat": 1, "lng": 2, "label": "Дом"})
        make(crm_client, crm_auth, "Глеб")

        assert names(crm_client, crm_auth, has_place="false") == ["Глеб"]
        assert names(crm_client, crm_auth, has_place="true") == ["Анна", "Борис", "Вера"]

    def test_filters_combine_with_search(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", company="Acme")
        make(crm_client, crm_auth, "Анатолий")

        assert names(crm_client, crm_auth, q="Ан", has_frequency="false", has_priority="false") == ["Анатолий", "Анна"]

    def test_bad_inactive_days_is_422(self, crm_client, crm_auth):
        assert crm_client.get("/api/contacts/?inactive_days=0", headers=crm_auth).status_code == 422


class TestCount:
    def test_count_respects_filters(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", tags=["друг"])
        make(crm_client, crm_auth, "Борис")

        assert crm_client.get("/api/contacts/count", headers=crm_auth).json() == {"count": 2}
        assert crm_client.get("/api/contacts/count?tag=друг", headers=crm_auth).json() == {"count": 1}
        assert crm_client.get("/api/contacts/count?q=Бор", headers=crm_auth).json() == {"count": 1}

    def test_count_is_not_a_contact_id(self, crm_client, crm_auth):
        assert crm_client.get("/api/contacts/count", headers=crm_auth).status_code == 200

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/contacts/count").status_code == 401


class TestPlaces:
    def test_places_group_people(self, crm_client, crm_auth):
        a = make(crm_client, crm_auth, "Анна", address="Офис на Тверской", city="Москва")
        b = make(crm_client, crm_auth, "Борис", address="Офис на Тверской", city="Москва")
        v = make(crm_client, crm_auth, "Вера", city="Казань")
        make(crm_client, crm_auth, "Глеб")

        places = crm_client.get("/api/places", headers=crm_auth).json()

        by_name = {p["name"]: p for p in places}
        assert set(by_name) == {"Офис на Тверской", "Казань"}
        office = by_name["Офис на Тверской"]
        assert office["city"] == "Москва" and office["count"] == 2
        assert {c["id"] for c in office["contacts"]} == {a["id"], b["id"]}
        assert by_name["Казань"]["contacts"][0]["id"] == v["id"]

    def test_place_takes_location_from_people(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", address="Дом", location={"lat": 55.7, "lng": 37.6, "label": "Дом"})

        place = crm_client.get("/api/places", headers=crm_auth).json()[0]

        assert place["location"] == {"lat": 55.7, "lng": 37.6, "label": "Дом"}

    def test_location_label_names_place_without_address(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", location={"lat": 1, "lng": 2, "label": "Кафе"})

        assert [p["name"] for p in crm_client.get("/api/places", headers=crm_auth).json()] == ["Кафе"]

    def test_created_empty_place_is_listed(self, crm_client, crm_auth):
        resp = crm_client.post("/api/places", json={"name": " Коворкинг ", "city": "Питер"}, headers=crm_auth)

        assert resp.status_code == 201
        assert resp.json()["name"] == "Коворкинг" and resp.json()["count"] == 0
        listed = crm_client.get("/api/places", headers=crm_auth).json()
        assert [(p["name"], p["city"], p["count"]) for p in listed] == [("Коворкинг", "Питер", 0)]

    def test_created_place_merges_with_contacts_place(self, crm_client, crm_auth):
        crm_client.post("/api/places", json={"name": "Дом", "city": "Москва"}, headers=crm_auth)
        make(crm_client, crm_auth, "Анна", address="Дом", city="Москва")

        listed = crm_client.get("/api/places", headers=crm_auth).json()

        assert len(listed) == 1 and listed[0]["count"] == 1

    def test_place_name_required_and_unique(self, crm_client, crm_auth):
        assert crm_client.post("/api/places", json={"name": " "}, headers=crm_auth).status_code == 422
        crm_client.post("/api/places", json={"name": "Дом"}, headers=crm_auth)
        assert crm_client.post("/api/places", json={"name": "дом"}, headers=crm_auth).status_code == 409

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/places").status_code == 401
