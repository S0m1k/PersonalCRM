"""
Сохранённые виды списка контактов: /api/views.
"""

from __future__ import annotations

VIEW = {
    "name": "Друзья",
    "emoji": "🎉",
    "filters": {"tag": "друг", "has_frequency": False},
    "sort": "name",
    "columns": ["name", "company", "frequency"],
}


def make_view(client, auth, **extra) -> dict:
    resp = client.post("/api/views", json={**VIEW, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestViews:
    def test_create_and_list(self, crm_client, crm_auth):
        view = make_view(crm_client, crm_auth)
        make_view(crm_client, crm_auth, name="Алфавит", emoji="")

        views = crm_client.get("/api/views", headers=crm_auth).json()

        assert [v["name"] for v in views] == ["Друзья", "Алфавит"]  # по порядку создания
        assert views[0]["id"] == view["id"] and "_id" not in views[0]
        assert views[0]["filters"] == VIEW["filters"]
        assert views[0]["sort"] == "name" and views[0]["columns"] == VIEW["columns"]
        assert views[0]["created_at"]

    def test_defaults(self, crm_client, crm_auth):
        resp = crm_client.post("/api/views", json={"name": "Пустой"}, headers=crm_auth)

        assert resp.status_code == 201
        assert resp.json()["filters"] == {} and resp.json()["sort"] is None and resp.json()["columns"] == []

    def test_name_required_and_trimmed(self, crm_client, crm_auth):
        assert crm_client.post("/api/views", json={"name": "  "}, headers=crm_auth).status_code == 422
        assert make_view(crm_client, crm_auth, name="  Клуб ")["name"] == "Клуб"

    def test_invalid_sort_is_422(self, crm_client, crm_auth):
        resp = crm_client.post("/api/views", json={"name": "x", "sort": "random"}, headers=crm_auth)

        assert resp.status_code == 422

    def test_duplicate_name_is_conflict(self, crm_client, crm_auth):
        make_view(crm_client, crm_auth)

        assert crm_client.post("/api/views", json={"name": "друзья"}, headers=crm_auth).status_code == 409

    def test_get_one(self, crm_client, crm_auth):
        view = make_view(crm_client, crm_auth)

        assert crm_client.get(f"/api/views/{view['id']}", headers=crm_auth).json()["name"] == "Друзья"
        assert crm_client.get("/api/views/64b000000000000000000000", headers=crm_auth).status_code == 404

    def test_update(self, crm_client, crm_auth):
        view = make_view(crm_client, crm_auth)
        other = make_view(crm_client, crm_auth, name="Другой")

        resp = crm_client.patch(
            f"/api/views/{view['id']}", json={"name": "Близкие", "filters": {"priority": "top"}}, headers=crm_auth
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "Близкие" and resp.json()["filters"] == {"priority": "top"}
        assert resp.json()["columns"] == VIEW["columns"]  # не переданное не меняется
        clash = crm_client.patch(f"/api/views/{other['id']}", json={"name": "близкие"}, headers=crm_auth)
        assert clash.status_code == 409

    def test_update_missing_is_404(self, crm_client, crm_auth):
        for vid in ("64b000000000000000000000", "не-id"):
            assert crm_client.patch(f"/api/views/{vid}", json={"emoji": "x"}, headers=crm_auth).status_code == 404

    def test_delete(self, crm_client, crm_auth):
        view = make_view(crm_client, crm_auth)

        assert crm_client.delete(f"/api/views/{view['id']}", headers=crm_auth).status_code == 204
        assert crm_client.get("/api/views", headers=crm_auth).json() == []
        assert crm_client.delete(f"/api/views/{view['id']}", headers=crm_auth).status_code == 404

    def test_views_are_per_user(self, crm_client, crm_auth):
        make_view(crm_client, crm_auth)
        resp = crm_client.post("/api/auth/register", json={"email": "boris@example.com", "password": "password-123"})
        boris = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        assert crm_client.get("/api/views", headers=boris).json() == []

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/views").status_code == 401
