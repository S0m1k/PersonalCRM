"""
Sprint 11: новые поля контакта (теги, группы, keep in touch, соцсети, место, оси Priority Map),
фильтры и сортировка списка, /api/tags.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.contact import ContactBase, ContactOut, ContactUpdate, KeepInTouch, Location, Social, normalize_labels


def make(client, auth, first_name="Анна", **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": first_name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestModels:
    def test_tags_are_trimmed_deduped_case_insensitively(self):
        assert normalize_labels(["  Друг ", "друг", "ДРУГ", "", "Коллега"]) == ["Друг", "Коллега"]

    def test_tag_longer_than_50_is_rejected(self):
        with pytest.raises(ValidationError):
            ContactBase(tags=["я" * 51])

    def test_more_than_50_tags_are_rejected(self):
        with pytest.raises(ValidationError):
            ContactBase(tags=[f"t{i}" for i in range(51)])

    def test_labels_must_be_a_list(self):
        with pytest.raises(ValidationError):
            ContactBase(tags="друг")

    def test_life_areas_are_normalized_like_tags(self):
        assert ContactBase(life_areas=["Семья", "семья ", "Работа"]).life_areas == ["Семья", "Работа"]

    @pytest.mark.parametrize("days", [0, 731, -5])
    def test_frequency_out_of_range(self, days):
        with pytest.raises(ValidationError):
            KeepInTouch(frequency_days=days)

    def test_frequency_bounds_are_ok(self):
        assert KeepInTouch(frequency_days=1).frequency_days == 1
        assert KeepInTouch(frequency_days=730).frequency_days == 730

    def test_snoozed_until_is_validated_and_stored_as_iso_string(self):
        assert KeepInTouch(snoozed_until="2026-12-01").snoozed_until == "2026-12-01"
        with pytest.raises(ValidationError):
            KeepInTouch(snoozed_until="завтра")

    @pytest.mark.parametrize("lat,lng", [(91, 0), (-91, 0), (0, 181), (0, -181)])
    def test_location_range(self, lat, lng):
        with pytest.raises(ValidationError):
            Location(lat=lat, lng=lng)

    @pytest.mark.parametrize("value", ["javascript:alert(1)", "data:text/html,x", "ftp://x.y/z", "not a link", "<b>"])
    def test_social_rejects_dangerous_or_garbage_values(self, value):
        with pytest.raises(ValidationError):
            Social(linkedin=value)

    @pytest.mark.parametrize("value", ["https://linkedin.com/in/anna", "http://example.org", "@anna_k", "anna.k"])
    def test_social_accepts_urls_and_handles(self, value):
        assert Social(telegram=value).telegram == value

    def test_social_empty_and_none_become_empty_string(self):
        assert Social(telegram=None, twitter="  ").telegram == ""

    @pytest.mark.parametrize("field", ["importance", "closeness"])
    @pytest.mark.parametrize("value", [0, 6])
    def test_axes_range(self, field, value):
        with pytest.raises(ValidationError):
            ContactBase(**{field: value})

    def test_first_met_at_must_be_a_date(self):
        assert ContactBase(first_met_at="2020-05-01").first_met_at == "2020-05-01"
        assert ContactBase(first_met_at="").first_met_at is None
        with pytest.raises(ValidationError):
            ContactBase(first_met_at="01.05.2020")

    def test_old_documents_without_new_fields_still_load(self):
        now = datetime.now(timezone.utc)
        out = ContactOut.from_mongo(
            {"_id": __import__("bson").ObjectId(), "first_name": "Старый", "created_at": now, "updated_at": now}
        )

        assert out.tags == [] and out.group_ids == [] and out.description == ""
        assert out.keep_in_touch.frequency_days is None
        assert out.location is None and out.importance is None and out.last_interaction_at is None
        assert out.social.telegram == ""

    def test_update_model_normalizes_labels_and_keeps_none_as_not_set(self):
        update = ContactUpdate(tags=[" a ", "A"], group_ids=["1", "1", "2"])

        assert update.tags == ["a"] and update.group_ids == ["1", "2"]
        assert ContactUpdate().tags is None


class TestContactApi:
    def test_new_fields_roundtrip(self, crm_client, crm_auth):
        group = crm_client.post("/api/groups", json={"name": "Семья"}, headers=crm_auth).json()
        created = make(
            crm_client,
            crm_auth,
            description="Школьная подруга",
            tags=["Друг", "друг"],
            group_ids=[group["id"]],
            keep_in_touch={"frequency_days": 30},
            first_met_at="2010-09-01",
            first_met_note="В школе",
            address="Москва, Тверская 1",
            location={"lat": 55.75, "lng": 37.61, "label": "Дом"},
            social={"telegram": "@anna", "linkedin": "https://linkedin.com/in/anna"},
            importance=4,
            closeness=5,
            life_areas=["Друзья"],
        )

        fetched = crm_client.get(f"/api/contacts/{created['id']}", headers=crm_auth).json()

        assert fetched["tags"] == ["Друг"]
        assert fetched["group_ids"] == [group["id"]]
        assert fetched["keep_in_touch"] == {"frequency_days": 30, "snoozed_until": None}
        assert fetched["location"] == {"lat": 55.75, "lng": 37.61, "label": "Дом"}
        assert fetched["social"]["telegram"] == "@anna"
        assert (fetched["importance"], fetched["closeness"]) == (4, 5)
        assert fetched["first_met_at"] == "2010-09-01"
        assert fetched["last_interaction_at"] is None

    def test_defaults_for_plain_contact(self, crm_client, crm_auth):
        created = make(crm_client, crm_auth)

        assert created["tags"] == [] and created["group_ids"] == []
        assert created["keep_in_touch"] == {"frequency_days": None, "snoozed_until": None}
        assert created["location"] is None

    def test_last_interaction_at_is_read_only_for_clients(self, crm_client, crm_auth):
        created = make(crm_client, crm_auth, last_interaction_at="2020-01-01T00:00:00Z")
        patched = crm_client.patch(
            f"/api/contacts/{created['id']}", json={"last_interaction_at": "2021-01-01T00:00:00Z"}, headers=crm_auth
        ).json()

        assert created["last_interaction_at"] is None and patched["last_interaction_at"] is None

    def test_invalid_values_are_422(self, crm_client, crm_auth):
        for bad in (
            {"social": {"website": "javascript:alert(1)"}},
            {"keep_in_touch": {"frequency_days": 0}},
            {"location": {"lat": 100, "lng": 0}},
            {"importance": 9},
        ):
            resp = crm_client.post("/api/contacts/", json={"first_name": "X", **bad}, headers=crm_auth)
            assert resp.status_code == 422, bad

    def test_unknown_group_is_422(self, crm_client, crm_auth):
        resp = crm_client.post(
            "/api/contacts/", json={"first_name": "X", "group_ids": ["64b000000000000000000000"]}, headers=crm_auth
        )
        assert resp.status_code == 422
        created = make(crm_client, crm_auth)
        resp = crm_client.patch(f"/api/contacts/{created['id']}", json={"group_ids": ["нет"]}, headers=crm_auth)
        assert resp.status_code == 422

    def test_patch_null_clears_nullable_fields_only(self, crm_client, crm_auth):
        created = make(
            crm_client, crm_auth, importance=3, closeness=2, location={"lat": 1, "lng": 2}, first_met_at="2020-01-01",
            description="био",
        )

        patched = crm_client.patch(
            f"/api/contacts/{created['id']}",
            json={"importance": None, "location": None, "first_met_at": None, "description": None},
            headers=crm_auth,
        ).json()

        assert patched["importance"] is None and patched["location"] is None and patched["first_met_at"] is None
        assert patched["closeness"] == 2  # не передавали — не менялось
        assert patched["description"] == "био"  # None у обычных полей — «не менять»

    def test_patch_without_nullable_keys_keeps_them(self, crm_client, crm_auth):
        created = make(crm_client, crm_auth, importance=3)

        patched = crm_client.patch(f"/api/contacts/{created['id']}", json={"company": "ACME"}, headers=crm_auth).json()

        assert patched["importance"] == 3


class TestListFilters:
    def test_filter_by_tag_case_insensitive(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", tags=["Друг"])
        make(crm_client, crm_auth, "Борис", tags=["Коллега"])

        found = crm_client.get("/api/contacts/", params={"tag": "друг"}, headers=crm_auth).json()

        assert [c["first_name"] for c in found] == ["Анна"]

    def test_tag_filter_is_exact_not_substring(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", tags=["друзья детства"])

        assert crm_client.get("/api/contacts/", params={"tag": "друг"}, headers=crm_auth).json() == []

    def test_filter_by_group(self, crm_client, crm_auth):
        group = crm_client.post("/api/groups", json={"name": "Клуб"}, headers=crm_auth).json()
        make(crm_client, crm_auth, "Анна", group_ids=[group["id"]])
        make(crm_client, crm_auth, "Борис")

        found = crm_client.get("/api/contacts/", params={"group_id": group["id"]}, headers=crm_auth).json()

        assert [c["first_name"] for c in found] == ["Анна"]

    def test_has_location(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", location={"lat": 1, "lng": 1})
        make(crm_client, crm_auth, "Борис")

        with_loc = crm_client.get("/api/contacts/", params={"has_location": True}, headers=crm_auth).json()
        without = crm_client.get("/api/contacts/", params={"has_location": False}, headers=crm_auth).json()

        assert [c["first_name"] for c in with_loc] == ["Анна"]
        assert [c["first_name"] for c in without] == ["Борис"]

    def test_sorts(self, crm_client, crm_auth):
        a = make(crm_client, crm_auth, "Яна", importance=1)
        b = make(crm_client, crm_auth, "Анна", importance=5)
        crm_client.post("/api/interactions", json={"contact_ids": [a["id"]], "title": "звонок"}, headers=crm_auth)

        def names(sort):
            resp = crm_client.get("/api/contacts/", params={"sort": sort}, headers=crm_auth).json()
            return [c["first_name"] for c in resp]

        assert names("name") == ["Анна", "Яна"]
        assert names("importance") == ["Анна", "Яна"]
        assert names("created") == ["Анна", "Яна"]
        assert names("last_interaction")[0] == "Яна"

    def test_unknown_sort_is_422(self, crm_client, crm_auth):
        assert crm_client.get("/api/contacts/", params={"sort": "по-луне"}, headers=crm_auth).status_code == 422


class TestTagsApi:
    def test_list_counts_case_insensitive(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "А", tags=["Друг", "Бег"])
        make(crm_client, crm_auth, "Б", tags=["друг"])
        make(crm_client, crm_auth, "В", tags=["Друг"])

        tags = crm_client.get("/api/tags", headers=crm_auth).json()

        assert tags == [{"tag": "Друг", "count": 3}, {"tag": "Бег", "count": 1}]

    def test_rename(self, crm_client, crm_auth):
        c = make(crm_client, crm_auth, "А", tags=["друг"])

        resp = crm_client.post("/api/tags/rename", json={"from": "Друг", "to": "Близкий"}, headers=crm_auth)

        assert resp.json() == {"updated": 1}
        assert crm_client.get(f"/api/contacts/{c['id']}", headers=crm_auth).json()["tags"] == ["Близкий"]

    def test_rename_into_existing_tag_merges_without_duplicates(self, crm_client, crm_auth):
        both = make(crm_client, crm_auth, "А", tags=["a", "b"])
        only_a = make(crm_client, crm_auth, "Б", tags=["a"])

        crm_client.post("/api/tags/rename", json={"from": "a", "to": "B"}, headers=crm_auth)

        assert crm_client.get(f"/api/contacts/{both['id']}", headers=crm_auth).json()["tags"] == ["B"]
        assert crm_client.get(f"/api/contacts/{only_a['id']}", headers=crm_auth).json()["tags"] == ["B"]
        assert crm_client.get("/api/tags", headers=crm_auth).json() == [{"tag": "B", "count": 2}]

    def test_rename_validates_input(self, crm_client, crm_auth):
        assert crm_client.post("/api/tags/rename", json={"from": "a", "to": ""}, headers=crm_auth).status_code == 422
        assert crm_client.post("/api/tags/rename", json={"from": "a", "to": " "}, headers=crm_auth).status_code == 422
        too_long = "я" * 51
        assert crm_client.post("/api/tags/rename", json={"from": "a", "to": too_long}, headers=crm_auth).status_code == 422

    def test_delete_removes_tag_from_all_contacts(self, crm_client, crm_auth):
        c = make(crm_client, crm_auth, "А", tags=["лишний", "нужный"])
        make(crm_client, crm_auth, "Б", tags=["Лишний"])

        resp = crm_client.delete("/api/tags/лишний", headers=crm_auth)

        assert resp.json() == {"updated": 2}
        assert crm_client.get(f"/api/contacts/{c['id']}", headers=crm_auth).json()["tags"] == ["нужный"]

    def test_delete_unknown_tag_changes_nothing(self, crm_client, crm_auth):
        assert crm_client.delete("/api/tags/нет", headers=crm_auth).json() == {"updated": 0}

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/tags").status_code == 401
