"""
Timeline: /api/interactions — CRUD, фильтры, курсорная пагинация, last_interaction_at,
подмешивание прошедших событий календаря.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

INTERACTIONS = "/api/interactions"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


def iso(delta_days: float) -> str:
    return (NOW + timedelta(days=delta_days)).isoformat()


def make_contact(client, auth, name="Анна", **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def log(client, auth, contact_ids, days_ago=0, **extra) -> dict:
    body = {"contact_ids": contact_ids, "title": "Заметка", "occurred_at": iso(-days_ago), **extra}
    resp = client.post(INTERACTIONS, json=body, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def event(client, auth, contact_ids, days_ago, title="Обед") -> dict:
    start = NOW - timedelta(days=days_ago)
    body = {
        "title": title,
        "start": start.isoformat(),
        "end": (start + timedelta(hours=1)).isoformat(),
        "contact_ids": contact_ids,
    }
    resp = client.post("/api/calendar/events", json=body, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def last_interaction(client, auth, contact_id) -> str | None:
    return client.get(f"/api/contacts/{contact_id}", headers=auth).json()["last_interaction_at"]


def same_moment(value: str | None, expected: str) -> bool:
    return value is not None and datetime.fromisoformat(value) == datetime.fromisoformat(expected)


class TestCrud:
    def test_create_defaults(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)

        resp = crm_client.post(INTERACTIONS, json={"contact_ids": [anna["id"]]}, headers=crm_auth)

        assert resp.status_code == 201
        body = resp.json()
        assert body["kind"] == "note" and body["source"] == "manual" and body["read_only"] is False
        assert body["contact_ids"] == [anna["id"]] and "_id" not in body
        assert datetime.fromisoformat(body["occurred_at"]) > NOW - timedelta(minutes=5)

    def test_create_validates(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        for bad in (
            {"contact_ids": [anna["id"]], "kind": "телепатия"},
            {"contact_ids": [anna["id"]], "source": "hack"},
            {"contact_ids": [anna["id"]], "title": "я" * 301},
            {"contact_ids": [anna["id"]], "occurred_at": "вчера"},
        ):
            assert crm_client.post(INTERACTIONS, json=bad, headers=crm_auth).status_code == 422, bad

    def test_unknown_contact_is_422(self, crm_client, crm_auth):
        resp = crm_client.post(INTERACTIONS, json={"contact_ids": ["64b000000000000000000000"]}, headers=crm_auth)

        assert resp.status_code == 422

    def test_update_and_delete(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        created = log(crm_client, crm_auth, [anna["id"]])

        updated = crm_client.patch(
            f"{INTERACTIONS}/{created['id']}", json={"title": "Звонок", "kind": "call", "body": "О планах"}, headers=crm_auth
        )

        assert updated.status_code == 200
        assert (updated.json()["title"], updated.json()["kind"], updated.json()["body"]) == ("Звонок", "call", "О планах")
        assert crm_client.delete(f"{INTERACTIONS}/{created['id']}", headers=crm_auth).status_code == 204
        assert crm_client.get(INTERACTIONS, headers=crm_auth).json()["items"] == []

    def test_missing_is_404(self, crm_client, crm_auth):
        for iid in ("64b000000000000000000000", "плохой"):
            assert crm_client.patch(f"{INTERACTIONS}/{iid}", json={"title": "x"}, headers=crm_auth).status_code == 404
            assert crm_client.delete(f"{INTERACTIONS}/{iid}", headers=crm_auth).status_code == 404

    def test_update_with_unknown_contact_is_422(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        created = log(crm_client, crm_auth, [anna["id"]])

        resp = crm_client.patch(f"{INTERACTIONS}/{created['id']}", json={"contact_ids": ["64b000000000000000000000"]}, headers=crm_auth)

        assert resp.status_code == 422

    def test_calendar_items_are_read_only(self, crm_client, crm_auth):
        resp = crm_client.patch(f"{INTERACTIONS}/event:64b000000000000000000000", json={"title": "x"}, headers=crm_auth)
        assert resp.status_code == 409
        resp = crm_client.delete(f"{INTERACTIONS}/event:64b000000000000000000000", headers=crm_auth)
        assert resp.status_code == 409

    def test_requires_auth(self, crm_client):
        assert crm_client.get(INTERACTIONS).status_code == 401


class TestLastInteraction:
    def test_is_max_occurred_at(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        log(crm_client, crm_auth, [anna["id"]], days_ago=10)
        newest = log(crm_client, crm_auth, [anna["id"]], days_ago=2)
        log(crm_client, crm_auth, [anna["id"]], days_ago=5)

        assert same_moment(last_interaction(crm_client, crm_auth, anna["id"]), newest["occurred_at"])

    def test_future_interaction_does_not_count(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        past = log(crm_client, crm_auth, [anna["id"]], days_ago=3)
        log(crm_client, crm_auth, [anna["id"]], days_ago=-5)

        assert same_moment(last_interaction(crm_client, crm_auth, anna["id"]), past["occurred_at"])

    def test_recomputed_on_update_delete_and_contact_change(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth, "Анна")
        boris = make_contact(crm_client, crm_auth, "Борис")
        old = log(crm_client, crm_auth, [anna["id"]], days_ago=9)
        new = log(crm_client, crm_auth, [anna["id"]], days_ago=1)

        crm_client.delete(f"{INTERACTIONS}/{new['id']}", headers=crm_auth)
        assert same_moment(last_interaction(crm_client, crm_auth, anna["id"]), old["occurred_at"])

        crm_client.patch(f"{INTERACTIONS}/{old['id']}", json={"occurred_at": iso(-4)}, headers=crm_auth)
        assert same_moment(last_interaction(crm_client, crm_auth, anna["id"]), iso(-4))

        crm_client.patch(f"{INTERACTIONS}/{old['id']}", json={"contact_ids": [boris["id"]]}, headers=crm_auth)
        assert last_interaction(crm_client, crm_auth, anna["id"]) is None
        assert same_moment(last_interaction(crm_client, crm_auth, boris["id"]), iso(-4))

    def test_past_calendar_event_counts(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        log(crm_client, crm_auth, [anna["id"]], days_ago=20)
        ev = event(crm_client, crm_auth, [anna["id"]], days_ago=6)

        assert same_moment(last_interaction(crm_client, crm_auth, anna["id"]), ev["start"])

        crm_client.delete(f"/api/calendar/events/{ev['id']}", headers=crm_auth)
        assert same_moment(last_interaction(crm_client, crm_auth, anna["id"]), iso(-20))

    def test_future_event_does_not_count(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        event(crm_client, crm_auth, [anna["id"]], days_ago=-4)

        assert last_interaction(crm_client, crm_auth, anna["id"]) is None

    def test_moving_event_to_another_person_recomputes_both(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth, "Анна")
        boris = make_contact(crm_client, crm_auth, "Борис")
        ev = event(crm_client, crm_auth, [anna["id"]], days_ago=3)

        crm_client.patch(f"/api/calendar/events/{ev['id']}", json={"contact_ids": [boris["id"]]}, headers=crm_auth)

        assert last_interaction(crm_client, crm_auth, anna["id"]) is None
        assert same_moment(last_interaction(crm_client, crm_auth, boris["id"]), ev["start"])

    def test_deleting_contact_removes_it_from_interactions(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth, "Анна")
        boris = make_contact(crm_client, crm_auth, "Борис")
        solo = log(crm_client, crm_auth, [anna["id"]], title="Только Анна")
        shared = log(crm_client, crm_auth, [anna["id"], boris["id"]], title="Вдвоём")

        crm_client.delete(f"/api/contacts/{anna['id']}", headers=crm_auth)

        items = crm_client.get(INTERACTIONS, headers=crm_auth).json()["items"]
        assert [i["id"] for i in items] == [shared["id"]]
        assert items[0]["contact_ids"] == [boris["id"]]
        assert solo["id"] not in [i["id"] for i in items]


class TestListing:
    def test_newest_first_and_filters(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth, "Анна")
        boris = make_contact(crm_client, crm_auth, "Борис")
        log(crm_client, crm_auth, [anna["id"]], days_ago=3, title="Кофе", kind="meeting")
        log(crm_client, crm_auth, [boris["id"]], days_ago=2, title="Созвон по проекту", kind="call", body="бюджет")
        log(crm_client, crm_auth, [anna["id"], boris["id"]], days_ago=1, title="Ужин вдвоём", kind="meeting")

        def titles(**params):
            resp = crm_client.get(INTERACTIONS, params=params, headers=crm_auth)
            assert resp.status_code == 200, resp.text
            return [i["title"] for i in resp.json()["items"]]

        assert titles() == ["Ужин вдвоём", "Созвон по проекту", "Кофе"]
        assert titles(contact_id=anna["id"]) == ["Ужин вдвоём", "Кофе"]
        assert titles(kind="call") == ["Созвон по проекту"]
        assert titles(q="БЮДЖЕТ") == ["Созвон по проекту"]
        assert titles(q="ужин") == ["Ужин вдвоём"]
        assert titles(**{"from": iso(-2.5), "to": iso(-1.5)}) == ["Созвон по проекту"]

    def test_repeated_kind_and_contact_id_are_or_filters(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth, "Анна")
        boris = make_contact(crm_client, crm_auth, "Борис")
        vera = make_contact(crm_client, crm_auth, "Вера")
        log(crm_client, crm_auth, [anna["id"]], days_ago=3, title="A", kind="meeting")
        log(crm_client, crm_auth, [boris["id"]], days_ago=2, title="B", kind="call")
        log(crm_client, crm_auth, [vera["id"]], days_ago=1, title="V", kind="email")

        def titles(**params):
            resp = crm_client.get(INTERACTIONS, params=params, headers=crm_auth)
            assert resp.status_code == 200, resp.text
            return [i["title"] for i in resp.json()["items"]]

        assert titles(kind=["meeting", "call"]) == ["B", "A"]
        assert titles(contact_id=[anna["id"], vera["id"]]) == ["V", "A"]
        assert titles(kind=["email", "call"], contact_id=[boris["id"], vera["id"]]) == ["V", "B"]

    def test_search_text_is_not_a_regex(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        log(crm_client, crm_auth, [anna["id"]], title="a.b")
        log(crm_client, crm_auth, [anna["id"]], title="axb")

        resp = crm_client.get(INTERACTIONS, params={"q": "a.b"}, headers=crm_auth).json()

        assert [i["title"] for i in resp["items"]] == ["a.b"]

    def test_cursor_pagination_covers_everything_once(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        for days in range(7):
            log(crm_client, crm_auth, [anna["id"]], days_ago=days, title=f"n{days}")

        seen: list[str] = []
        cursor = None
        pages = 0
        while True:
            params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
            page = crm_client.get(INTERACTIONS, params=params, headers=crm_auth).json()
            seen += [i["title"] for i in page["items"]]
            pages += 1
            cursor = page["next_cursor"]
            if not cursor:
                break

        assert seen == [f"n{d}" for d in range(7)]
        assert pages == 3

    def test_equal_timestamps_do_not_skip_or_repeat(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        stamp = iso(-1)
        for i in range(5):
            log(crm_client, crm_auth, [anna["id"]], title=f"same{i}", occurred_at=stamp)

        first = crm_client.get(INTERACTIONS, params={"limit": 2}, headers=crm_auth).json()
        second = crm_client.get(INTERACTIONS, params={"limit": 2, "cursor": first["next_cursor"]}, headers=crm_auth).json()
        third = crm_client.get(INTERACTIONS, params={"limit": 2, "cursor": second["next_cursor"]}, headers=crm_auth).json()

        ids = [i["id"] for page in (first, second, third) for i in page["items"]]
        assert len(ids) == 5 and len(set(ids)) == 5
        assert third["next_cursor"] is None

    def test_bad_cursor_is_422(self, crm_client, crm_auth):
        assert crm_client.get(INTERACTIONS, params={"cursor": "!!!"}, headers=crm_auth).status_code == 422

    def test_limit_bounds(self, crm_client, crm_auth):
        assert crm_client.get(INTERACTIONS, params={"limit": 0}, headers=crm_auth).status_code == 422
        assert crm_client.get(INTERACTIONS, params={"limit": 201}, headers=crm_auth).status_code == 422


class TestIncludeEvents:
    def test_events_are_merged_as_read_only_meetings(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        log(crm_client, crm_auth, [anna["id"]], days_ago=5, title="Заметка")
        ev = event(crm_client, crm_auth, [anna["id"]], days_ago=2, title="Обед")
        event(crm_client, crm_auth, [anna["id"]], days_ago=-3, title="Будущая")  # в будущем — не в ленте
        event(crm_client, crm_auth, [], days_ago=1, title="Без людей")

        plain = crm_client.get(INTERACTIONS, params={"contact_id": anna["id"]}, headers=crm_auth).json()["items"]
        merged = crm_client.get(
            INTERACTIONS, params={"contact_id": anna["id"], "include_events": True}, headers=crm_auth
        ).json()["items"]

        assert [i["title"] for i in plain] == ["Заметка"]
        assert [i["title"] for i in merged] == ["Обед", "Заметка"]
        meeting = merged[0]
        assert meeting["id"] == f"event:{ev['id']}"
        assert (meeting["kind"], meeting["source"], meeting["read_only"]) == ("meeting", "calendar", True)
        assert meeting["contact_ids"] == [anna["id"]]

    def test_global_feed_only_has_events_with_people(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        event(crm_client, crm_auth, [], days_ago=1, title="Без людей")
        event(crm_client, crm_auth, [anna["id"]], days_ago=2, title="С Анной")

        items = crm_client.get(INTERACTIONS, params={"include_events": True}, headers=crm_auth).json()["items"]

        assert [i["title"] for i in items] == ["С Анной"]

    def test_kind_filter_hides_events_unless_meeting(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        event(crm_client, crm_auth, [anna["id"]], days_ago=2, title="Обед")

        calls = crm_client.get(INTERACTIONS, params={"include_events": True, "kind": "call"}, headers=crm_auth).json()
        meetings = crm_client.get(
            INTERACTIONS, params={"include_events": True, "kind": "meeting"}, headers=crm_auth
        ).json()

        assert calls["items"] == []
        assert [i["title"] for i in meetings["items"]] == ["Обед"]

    def test_pagination_across_both_sources(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        titles = []
        for days in range(6):
            if days % 2:
                event(crm_client, crm_auth, [anna["id"]], days_ago=days, title=f"e{days}")
            else:
                log(crm_client, crm_auth, [anna["id"]], days_ago=days, title=f"n{days}")
            titles.append(f"{'e' if days % 2 else 'n'}{days}")

        seen: list[str] = []
        cursor = None
        while True:
            params = {"include_events": True, "limit": 2, **({"cursor": cursor} if cursor else {})}
            page = crm_client.get(INTERACTIONS, params=params, headers=crm_auth).json()
            seen += [i["title"] for i in page["items"]]
            cursor = page["next_cursor"]
            if not cursor:
                break

        assert seen == titles

    def test_search_and_range_apply_to_events(self, crm_client, crm_auth):
        anna = make_contact(crm_client, crm_auth)
        event(crm_client, crm_auth, [anna["id"]], days_ago=2, title="Обед")
        event(crm_client, crm_auth, [anna["id"]], days_ago=10, title="Ужин")

        by_text = crm_client.get(INTERACTIONS, params={"include_events": True, "q": "ужин"}, headers=crm_auth).json()
        by_range = crm_client.get(
            INTERACTIONS, params={"include_events": True, "from": iso(-5)}, headers=crm_auth
        ).json()

        assert [i["title"] for i in by_text["items"]] == ["Ужин"]
        assert [i["title"] for i in by_range["items"]] == ["Обед"]
