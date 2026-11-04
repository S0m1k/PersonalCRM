"""
Граф «Сеть»: /api/network — узлы, связи из карточек, совместные взаимодействия, min_weight, лимит.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.network import build_graph, together_edges

NOW = datetime.now(timezone.utc)


def make_contact(client, auth, name, **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def together(client, auth, ids, days_ago=1):
    when = (NOW - timedelta(days=days_ago)).isoformat()
    resp = client.post("/api/interactions", json={"contact_ids": ids, "occurred_at": when}, headers=auth)
    assert resp.status_code == 201, resp.text


def edge_set(graph, kind):
    return {(e["source"], e["target"]): e for e in graph["edges"] if e["kind"] == kind}


class TestUnits:
    def test_pair_counts_ignore_unknown_people_and_singletons(self):
        edges = together_edges([["a", "b"], ["b", "a", "x"], ["c"], []], {"a", "b", "c"}, min_weight=1)

        assert [(e.source, e.target, e.weight) for e in edges] == [("a", "b", 2)]

    def test_min_weight(self):
        edges = together_edges([["a", "b"], ["a", "b"], ["a", "c"]], {"a", "b", "c"}, min_weight=2)

        assert [(e.source, e.target) for e in edges] == [("a", "b")]

    def test_group_of_three_gives_three_pairs(self):
        assert len(together_edges([["a", "b", "c"]], {"a", "b", "c"}, min_weight=1)) == 3

    def test_empty_graph(self):
        graph = build_graph([], [], [])

        assert graph.nodes == [] and graph.edges == [] and graph.truncated is False


class TestApi:
    def test_nodes_have_card_summary(self, crm_client, crm_auth):
        group = crm_client.post("/api/groups", json={"name": "Семья"}, headers=crm_auth).json()
        anna = make_contact(
            crm_client, crm_auth, "Анна", last_name="Иванова", company="ACME", tags=["друг"],
            group_ids=[group["id"]], importance=5,
        )

        graph = crm_client.get("/api/network", headers=crm_auth).json()

        assert graph["truncated"] is False and graph["edges"] == []
        assert graph["nodes"] == [
            {
                "id": anna["id"], "name": "Анна Иванова", "company": "ACME", "group_ids": [group["id"]],
                "tags": ["друг"], "importance": 5,
            }
        ]

    def test_relationship_edges_are_deduplicated(self, crm_client, crm_auth):
        boris = make_contact(crm_client, crm_auth, "Борис")
        anna = make_contact(crm_client, crm_auth, "Анна", relationships=[{"contact_id": boris["id"], "label": "коллега"}])
        crm_client.patch(
            f"/api/contacts/{boris['id']}", json={"relationships": [{"contact_id": anna["id"], "label": ""}]}, headers=crm_auth
        )

        graph = crm_client.get("/api/network", headers=crm_auth).json()

        edges = [e for e in graph["edges"] if e["kind"] == "relationship"]
        assert len(edges) == 1 and edges[0]["label"] == "коллега"

    def test_relationship_to_missing_contact_is_skipped(self, crm_client, crm_auth):
        make_contact(crm_client, crm_auth, "Анна", relationships=[{"contact_id": "64b000000000000000000000", "label": "x"}])

        assert crm_client.get("/api/network", headers=crm_auth).json()["edges"] == []

    def test_together_edges_from_interactions_and_events(self, crm_client, crm_auth):
        a, b, c = (make_contact(crm_client, crm_auth, n) for n in "АБВ")
        together(crm_client, crm_auth, [a["id"], b["id"]])
        together(crm_client, crm_auth, [a["id"], b["id"], c["id"]])
        start = NOW - timedelta(days=3)
        crm_client.post(
            "/api/calendar/events",
            json={"title": "Обед", "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(),
                  "contact_ids": [b["id"], c["id"]]},
            headers=crm_auth,
        )
        future = NOW + timedelta(days=3)
        crm_client.post(
            "/api/calendar/events",
            json={"title": "Будущая", "start": future.isoformat(), "end": (future + timedelta(hours=1)).isoformat(),
                  "contact_ids": [a["id"], c["id"]]},
            headers=crm_auth,
        )
        together(crm_client, crm_auth, [a["id"]])  # один человек — не ребро

        graph = crm_client.get("/api/network", headers=crm_auth).json()
        weights = {frozenset(k): e["weight"] for k, e in edge_set(graph, "together").items()}

        assert weights == {
            frozenset({a["id"], b["id"]}): 2,
            frozenset({b["id"], c["id"]}): 2,
            frozenset({a["id"], c["id"]}): 1,
        }

    def test_min_weight_filters_together_edges_only(self, crm_client, crm_auth):
        a = make_contact(crm_client, crm_auth, "А")
        b = make_contact(crm_client, crm_auth, "Б", relationships=[])
        c = make_contact(crm_client, crm_auth, "В", relationships=[{"contact_id": a["id"], "label": "брат"}])
        together(crm_client, crm_auth, [a["id"], b["id"]])
        together(crm_client, crm_auth, [a["id"], b["id"]])
        together(crm_client, crm_auth, [a["id"], c["id"]])

        graph = crm_client.get("/api/network", params={"min_weight": 2}, headers=crm_auth).json()

        assert len(edge_set(graph, "together")) == 1
        assert len(edge_set(graph, "relationship")) == 1

    def test_min_weight_must_be_positive(self, crm_client, crm_auth):
        assert crm_client.get("/api/network", params={"min_weight": 0}, headers=crm_auth).status_code == 422

    def test_node_cap_keeps_most_important(self, crm_client, crm_auth, monkeypatch):
        from app.routers import network

        monkeypatch.setattr(network, "NODE_LIMIT", 2)
        make_contact(crm_client, crm_auth, "Низкий", importance=1)
        make_contact(crm_client, crm_auth, "Высокий", importance=5)
        make_contact(crm_client, crm_auth, "Средний", importance=3)

        graph = crm_client.get("/api/network", headers=crm_auth).json()

        assert graph["truncated"] is True
        assert [n["name"] for n in graph["nodes"]] == ["Высокий", "Средний"]

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/network").status_code == 401
