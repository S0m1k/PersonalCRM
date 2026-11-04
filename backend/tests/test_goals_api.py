"""
/api/goals: состояние, настройки, круги, метрики, следующие шаги, применение к контактам.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

GOALS = "/api/goals"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def make_contact(client, auth, name="Анна", **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def log(client, auth, contact_ids, days_ago=0) -> None:
    body = {"contact_ids": contact_ids, "title": "Встреча", "occurred_at": (NOW - timedelta(days=days_ago)).isoformat()}
    assert client.post("/api/interactions", json=body, headers=auth).status_code == 201


def choose(client, auth, primary, **extra) -> dict:
    resp = client.put(GOALS, json={"primary": primary, **extra}, headers=auth)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_requires_auth(crm_client):
    assert crm_client.get(GOALS).status_code == 401
    assert crm_client.get(f"{GOALS}/metrics").status_code == 401


def test_initial_state_has_catalogue_and_defaults(crm_client, crm_auth):
    body = crm_client.get(GOALS, headers=crm_auth).json()

    assert body["primary"] is None and body["enabled"] == [] and body["assignments"] == {}
    assert [a["id"] for a in body["catalogue"]] == ["max_contacts", "deep_relations", "life_balance", "custom"]
    assert body["settings"]["max_contacts"]["new_per_month"] == 8
    assert len(body["settings"]["deep_relations"]["circles"]) == 4


def test_choose_primary_and_enabled_and_persist(crm_client, crm_auth):
    choose(crm_client, crm_auth, "deep_relations", enabled=["max_contacts", "deep_relations", "max_contacts"])

    body = crm_client.get(GOALS, headers=crm_auth).json()
    assert body["primary"] == "deep_relations" and body["enabled"] == ["max_contacts"]
    assert body["updated_at"]


def test_changing_primary_keeps_enabled_and_clear_primary(crm_client, crm_auth):
    choose(crm_client, crm_auth, "max_contacts", enabled=["life_balance"])
    body = choose(crm_client, crm_auth, "life_balance")

    assert body["primary"] == "life_balance" and body["enabled"] == []

    cleared = crm_client.put(GOALS, json={"clear_primary": True}, headers=crm_auth).json()
    assert cleared["primary"] is None


def test_settings_are_validated_and_saved(crm_client, crm_auth):
    ok = crm_client.put(GOALS, json={"settings": {"max_contacts": {"new_per_month": 12}}}, headers=crm_auth)
    assert ok.status_code == 200 and ok.json()["settings"]["max_contacts"]["new_per_month"] == 12
    assert ok.json()["settings"]["max_contacts"]["frequency_days"] == 120

    for bad in (
        {"max_contacts": {"new_per_month": 1000}},
        {"max_contacts": {"hack": 1}},
        {"deep_relations": {"circles": []}},
        {"custom": {"rules": [{"kind": "tag", "value": "x", "frequency_days": 0}]}},
    ):
        resp = crm_client.put(GOALS, json={"settings": bad}, headers=crm_auth)
        assert resp.status_code == 422, bad
    assert crm_client.get(GOALS, headers=crm_auth).json()["settings"]["max_contacts"]["new_per_month"] == 12


def test_unknown_approach_is_rejected(crm_client, crm_auth):
    assert crm_client.put(GOALS, json={"primary": "magic"}, headers=crm_auth).status_code == 422
    assert crm_client.put(GOALS, json={"settings": {"magic": {}}}, headers=crm_auth).status_code == 422


def test_assignments_bulk_set_and_remove(crm_client, crm_auth):
    a, b = make_contact(crm_client, crm_auth, "А"), make_contact(crm_client, crm_auth, "Б")

    body = crm_client.put(f"{GOALS}/assignments", json={"assignments": {a["id"]: 1, b["id"]: 3}}, headers=crm_auth).json()
    assert body["assignments"] == {a["id"]: {"circle": 1}, b["id"]: {"circle": 3}}

    body = crm_client.put(f"{GOALS}/assignments", json={"assignments": {a["id"]: None}}, headers=crm_auth).json()
    assert body["assignments"] == {b["id"]: {"circle": 3}}


def test_assignments_validation(crm_client, crm_auth):
    a = make_contact(crm_client, crm_auth)

    assert crm_client.put(f"{GOALS}/assignments", json={"assignments": {a["id"]: 5}}, headers=crm_auth).status_code == 422
    assert crm_client.put(f"{GOALS}/assignments", json={"assignments": {"507f1f77bcf86cd799439011": 1}}, headers=crm_auth).status_code == 422
    assert crm_client.put(f"{GOALS}/assignments", json={"assignments": {"не-id": 1}}, headers=crm_auth).status_code == 422


def test_recommendations_empty_without_strategy_then_ranked(crm_client, crm_auth):
    old = make_contact(crm_client, crm_auth, "Давний")
    fresh = make_contact(crm_client, crm_auth, "Свежий")
    log(crm_client, crm_auth, [fresh["id"]], days_ago=1)
    assert crm_client.get(f"{GOALS}/recommendations", headers=crm_auth).json()["items"] == []

    choose(crm_client, crm_auth, "max_contacts", settings={"max_contacts": {"frequency_days": 30}})
    log(crm_client, crm_auth, [old["id"]], days_ago=100)

    body = crm_client.get(f"{GOALS}/recommendations", headers=crm_auth).json()
    assert body["primary"] == "max_contacts"
    assert [i["name"] for i in body["items"]] == ["Давний"]
    assert body["items"][0]["days_since"] >= 99 and body["items"][0]["reason"]


def test_recommendations_limit_param(crm_client, crm_auth):
    for i in range(4):
        make_contact(crm_client, crm_auth, f"К{i}", keep_in_touch={"frequency_days": 30})
    choose(crm_client, crm_auth, "custom", settings={"custom": {"rules": [{"kind": "tag", "value": "x", "frequency_days": 1}]}})
    assert crm_client.get(f"{GOALS}/recommendations", params={"limit": 0}, headers=crm_auth).status_code == 422
    assert crm_client.get(f"{GOALS}/recommendations", params={"limit": 2}, headers=crm_auth).status_code == 200


def test_metrics_for_each_approach_and_period(crm_client, crm_auth):
    a = make_contact(crm_client, crm_auth, "Мама", life_areas=["Семья"])
    log(crm_client, crm_auth, [a["id"]], days_ago=2)
    crm_client.put(f"{GOALS}/assignments", json={"assignments": {a["id"]: 1}}, headers=crm_auth)
    choose(crm_client, crm_auth, "life_balance", enabled=["deep_relations", "max_contacts", "custom"])

    body = crm_client.get(f"{GOALS}/metrics", params={"period": 90}, headers=crm_auth).json()

    assert body["period"] == 90 and body["primary"] == "life_balance"
    assert [m["id"] for m in body["approaches"]] == ["life_balance", "deep_relations", "max_contacts", "custom"]
    life = body["approaches"][0]
    assert {s["name"]: s["touches"] for s in life["spheres"]}["Семья"] == 1
    assert life["radar"] and life["period_days"] == 90
    assert body["approaches"][1]["circles"][0]["count"] == 1
    assert crm_client.get(f"{GOALS}/metrics", params={"period": 45}, headers=crm_auth).status_code == 422


def test_metrics_without_strategy_is_empty(crm_client, crm_auth):
    body = crm_client.get(f"{GOALS}/metrics", headers=crm_auth).json()

    assert body == {"period": 30, "primary": None, "approaches": []}


def freq(client, auth, contact_id):
    return client.get(f"/api/contacts/{contact_id}", headers=auth).json()["keep_in_touch"]["frequency_days"]


def test_apply_preview_then_apply_skips_manual_and_remembers_applied(crm_client, crm_auth):
    plain = make_contact(crm_client, crm_auth, "Обычный")
    manual = make_contact(crm_client, crm_auth, "Вручную", keep_in_touch={"frequency_days": 21})
    choose(crm_client, crm_auth, "max_contacts")

    preview = crm_client.post(f"{GOALS}/apply/preview", headers=crm_auth).json()
    assert (preview["will_change"], preview["skipped_manual"]) == (1, 1)
    assert preview["by_frequency"] == [{"frequency_days": 120, "count": 1}]
    assert freq(crm_client, crm_auth, plain["id"]) is None  # просмотр ничего не пишет

    result = crm_client.post(f"{GOALS}/apply", headers=crm_auth).json()
    assert result["changed"] == 1 and result["skipped_manual"] == 1
    assert freq(crm_client, crm_auth, plain["id"]) == 120 and freq(crm_client, crm_auth, manual["id"]) == 21

    # Стратегия сменила частоту — прежде применённое значение обновляется без «перезаписать»
    crm_client.put(GOALS, json={"settings": {"max_contacts": {"frequency_days": 60}}}, headers=crm_auth)
    again = crm_client.post(f"{GOALS}/apply", headers=crm_auth).json()
    assert again["changed"] == 1
    assert freq(crm_client, crm_auth, plain["id"]) == 60 and freq(crm_client, crm_auth, manual["id"]) == 21


def test_apply_overwrite_changes_manual(crm_client, crm_auth):
    manual = make_contact(crm_client, crm_auth, "Вручную", keep_in_touch={"frequency_days": 21})
    choose(crm_client, crm_auth, "max_contacts")

    preview = crm_client.post(f"{GOALS}/apply/preview", json={"overwrite": True}, headers=crm_auth).json()
    assert preview["will_change"] == 1

    assert crm_client.post(f"{GOALS}/apply", json={"overwrite": True}, headers=crm_auth).json()["changed"] == 1
    assert freq(crm_client, crm_auth, manual["id"]) == 120


def test_apply_without_strategy_changes_nothing(crm_client, crm_auth):
    c = make_contact(crm_client, crm_auth)

    assert crm_client.post(f"{GOALS}/apply", headers=crm_auth).json()["changed"] == 0
    assert freq(crm_client, crm_auth, c["id"]) is None


def test_apply_deep_relations_only_for_assigned(crm_client, crm_auth):
    a, b = make_contact(crm_client, crm_auth, "А"), make_contact(crm_client, crm_auth, "Б")
    crm_client.put(f"{GOALS}/assignments", json={"assignments": {a["id"]: 2}}, headers=crm_auth)
    choose(crm_client, crm_auth, "deep_relations")

    crm_client.post(f"{GOALS}/apply", headers=crm_auth)

    assert freq(crm_client, crm_auth, a["id"]) == 30 and freq(crm_client, crm_auth, b["id"]) is None
