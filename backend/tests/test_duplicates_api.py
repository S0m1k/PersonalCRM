"""
Слияние дублей: GET /api/contacts/duplicates, POST /api/contacts/duplicates/dismiss, POST /api/contacts/merge.
"""

from __future__ import annotations


def make(client, auth, first, last="", **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": first, "last_name": last, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def pairs(client, auth) -> list[dict]:
    resp = client.get("/api/contacts/duplicates", headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def ids(pair) -> set[str]:
    return {pair["a"]["id"], pair["b"]["id"]}


class TestSuggestions:
    def test_same_phone_in_different_formats(self, crm_client, crm_auth):
        a = make(crm_client, crm_auth, "Иван", "Петров", phones=[{"value": "+7 921 553-53-33"}])
        b = make(crm_client, crm_auth, "Ваня", "П.", phones=[{"value": "89215535333"}])
        make(crm_client, crm_auth, "Мария", "Сидорова", phones=[{"value": "+7 900 000-00-00"}])

        found = pairs(crm_client, crm_auth)

        assert len(found) == 1
        assert ids(found[0]) == {a["id"], b["id"]}
        assert found[0]["score"] == 100 and "совпадение телефона" in found[0]["reasons"]

    def test_same_email(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", emails=[{"value": "Anna@Example.com"}])
        make(crm_client, crm_auth, "Аня", emails=[{"value": "anna@example.com"}])

        assert len(pairs(crm_client, crm_auth)) == 1

    def test_similar_names(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Александр", "Иванов")
        make(crm_client, crm_auth, "Александр", "Иванова")
        make(crm_client, crm_auth, "Борис", "Сидоров")

        found = pairs(crm_client, crm_auth)

        assert len(found) == 1 and found[0]["score"] >= 70

    def test_swapped_name_order_is_found(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Иван", "Иванов", company="Acme")
        make(crm_client, crm_auth, "Иванов", "Иван", company="Acme")

        assert len(pairs(crm_client, crm_auth)) == 1

    def test_no_duplicates(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Анна", "Первая")
        make(crm_client, crm_auth, "Борис", "Второй")

        assert pairs(crm_client, crm_auth) == []

    def test_each_pair_listed_once_sorted_by_score(self, crm_client, crm_auth):
        make(crm_client, crm_auth, "Александр", "Иванов")
        make(crm_client, crm_auth, "Александр", "Иванова")
        make(crm_client, crm_auth, "Кто-то", phones=[{"value": "+79990001122"}])
        make(crm_client, crm_auth, "Другой", phones=[{"value": "+79990001122"}])

        found = pairs(crm_client, crm_auth)

        assert [p["score"] for p in found] == sorted((p["score"] for p in found), reverse=True)
        assert len(found) == 2
        assert "_id" not in found[0]["a"]

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/contacts/duplicates").status_code == 401


class TestDismiss:
    def test_dismissed_pair_disappears_and_stays_hidden(self, crm_client, crm_auth):
        a = make(crm_client, crm_auth, "Иван", phones=[{"value": "+79990001122"}])
        b = make(crm_client, crm_auth, "Ваня", phones=[{"value": "+79990001122"}])

        resp = crm_client.post("/api/contacts/duplicates/dismiss", json={"a_id": b["id"], "b_id": a["id"]}, headers=crm_auth)

        assert resp.status_code == 204
        assert pairs(crm_client, crm_auth) == []
        assert pairs(crm_client, crm_auth) == []  # запомнено

    def test_dismiss_is_idempotent_and_validates_ids(self, crm_client, crm_auth):
        a = make(crm_client, crm_auth, "Иван")
        b = make(crm_client, crm_auth, "Ваня")
        body = {"a_id": a["id"], "b_id": b["id"]}

        assert crm_client.post("/api/contacts/duplicates/dismiss", json=body, headers=crm_auth).status_code == 204
        assert crm_client.post("/api/contacts/duplicates/dismiss", json=body, headers=crm_auth).status_code == 204
        same = {"a_id": a["id"], "b_id": a["id"]}
        assert crm_client.post("/api/contacts/duplicates/dismiss", json=same, headers=crm_auth).status_code == 422


class TestMerge:
    def test_merge_combines_data_and_deletes_others(self, crm_client, crm_auth):
        keep = make(crm_client, crm_auth, "Иван", "Петров", phones=[{"value": "+79990001122"}], tags=["друг"])
        gone = make(
            crm_client,
            crm_auth,
            "Ваня",
            "Петров",
            phones=[{"value": "+79990001122"}, {"value": "+79991112233"}],
            emails=[{"value": "ivan@example.com"}],
            company="Acme",
            tags=["Друг", "бег"],
            description="Любит горы",
            keep_in_touch={"frequency_days": 30},
            priority="top",
        )

        resp = crm_client.post("/api/contacts/merge", json={"keep_id": keep["id"], "merge_ids": [gone["id"]]}, headers=crm_auth)

        assert resp.status_code == 200, resp.text
        merged = resp.json()
        assert merged["id"] == keep["id"] and merged["first_name"] == "Иван"
        assert [p["value"] for p in merged["phones"]] == ["+79990001122", "+79991112233"]
        assert merged["emails"][0]["value"] == "ivan@example.com"
        assert merged["company"] == "Acme" and merged["description"] == "Любит горы"
        assert merged["tags"] == ["друг", "бег"]
        assert merged["keep_in_touch"]["frequency_days"] == 30 and merged["priority"] == "top"
        assert crm_client.get(f"/api/contacts/{gone['id']}", headers=crm_auth).status_code == 404

    def test_merge_does_not_overwrite_keepers_fields(self, crm_client, crm_auth):
        keep = make(crm_client, crm_auth, "Иван", priority="low", description="Мой")
        gone = make(crm_client, crm_auth, "Ваня", priority="top", description="Чужой")

        merged = crm_client.post(
            "/api/contacts/merge", json={"keep_id": keep["id"], "merge_ids": [gone["id"]]}, headers=crm_auth
        ).json()

        assert merged["priority"] == "low" and merged["description"] == "Мой"

    def test_merge_unions_groups(self, crm_client, crm_auth):
        g1 = crm_client.post("/api/groups", json={"name": "Семья"}, headers=crm_auth).json()
        g2 = crm_client.post("/api/groups", json={"name": "Бег"}, headers=crm_auth).json()
        keep = make(crm_client, crm_auth, "Иван", group_ids=[g1["id"]])
        gone = make(crm_client, crm_auth, "Ваня", group_ids=[g1["id"], g2["id"]])

        merged = crm_client.post(
            "/api/contacts/merge", json={"keep_id": keep["id"], "merge_ids": [gone["id"]]}, headers=crm_auth
        ).json()

        assert merged["group_ids"] == [g1["id"], g2["id"]]

    def test_merge_moves_interactions_and_questions(self, crm_client, crm_auth):
        keep = make(crm_client, crm_auth, "Иван")
        gone = make(crm_client, crm_auth, "Ваня")
        crm_client.post(
            "/api/interactions",
            json={"contact_ids": [gone["id"]], "title": "Кофе", "occurred_at": "2026-01-05T10:00:00+00:00"},
            headers=crm_auth,
        )

        merged = crm_client.post(
            "/api/contacts/merge", json={"keep_id": keep["id"], "merge_ids": [gone["id"]]}, headers=crm_auth
        ).json()

        feed = crm_client.get(f"/api/interactions?contact_id={keep['id']}", headers=crm_auth).json()
        assert [i["title"] for i in feed["items"]] == ["Кофе"]
        assert feed["items"][0]["contact_ids"] == [keep["id"]]
        assert merged["last_interaction_at"].startswith("2026-01-05")

    def test_merge_many_and_cleans_dismissals(self, crm_client, crm_auth):
        keep = make(crm_client, crm_auth, "Иван")
        b = make(crm_client, crm_auth, "Ваня", phones=[{"value": "+79990001122"}])
        c = make(crm_client, crm_auth, "Ванька", phones=[{"value": "+79990001122"}])
        crm_client.post("/api/contacts/duplicates/dismiss", json={"a_id": b["id"], "b_id": c["id"]}, headers=crm_auth)

        resp = crm_client.post(
            "/api/contacts/merge", json={"keep_id": keep["id"], "merge_ids": [b["id"], c["id"]]}, headers=crm_auth
        )

        assert resp.status_code == 200
        assert crm_client.get("/api/contacts/count", headers=crm_auth).json() == {"count": 1}

    def test_merge_validation(self, crm_client, crm_auth):
        keep = make(crm_client, crm_auth, "Иван")
        url = "/api/contacts/merge"

        assert crm_client.post(url, json={"keep_id": keep["id"], "merge_ids": []}, headers=crm_auth).status_code == 422
        assert crm_client.post(url, json={"keep_id": keep["id"], "merge_ids": [keep["id"]]}, headers=crm_auth).status_code == 422
        missing = crm_client.post(
            url, json={"keep_id": keep["id"], "merge_ids": ["64b000000000000000000000"]}, headers=crm_auth
        )
        assert missing.status_code == 404
        assert crm_client.post(
            url, json={"keep_id": "64b000000000000000000000", "merge_ids": [keep["id"]]}, headers=crm_auth
        ).status_code == 404
        # ничего не удалено после ошибок
        assert crm_client.get(f"/api/contacts/{keep['id']}", headers=crm_auth).status_code == 200
