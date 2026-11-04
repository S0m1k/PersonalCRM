"""
Группы контактов: /api/groups.
"""

from __future__ import annotations


def make_contact(client, auth, name="Анна", **extra) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_group(client, auth, name="Семья", **extra) -> dict:
    resp = client.post("/api/groups", json={"name": name, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestGroups:
    def test_create_and_list_with_member_counts(self, crm_client, crm_auth):
        family = make_group(crm_client, crm_auth, "Семья", emoji="👪", color="#ff8800", description="Родные")
        make_group(crm_client, crm_auth, "Бег")
        make_contact(crm_client, crm_auth, "Анна", group_ids=[family["id"]])
        make_contact(crm_client, crm_auth, "Борис", group_ids=[family["id"]])

        groups = crm_client.get("/api/groups", headers=crm_auth).json()

        assert [(g["name"], g["member_count"]) for g in groups] == [("Бег", 0), ("Семья", 2)]
        assert groups[1]["emoji"] == "👪" and groups[1]["color"] == "#ff8800"
        assert "_id" not in groups[1]

    def test_name_is_required_and_trimmed(self, crm_client, crm_auth):
        assert crm_client.post("/api/groups", json={"name": "  "}, headers=crm_auth).status_code == 422
        assert crm_client.post("/api/groups", json={}, headers=crm_auth).status_code == 422
        assert make_group(crm_client, crm_auth, "  Клуб  ")["name"] == "Клуб"

    def test_duplicate_name_is_conflict(self, crm_client, crm_auth):
        make_group(crm_client, crm_auth, "Семья")

        assert crm_client.post("/api/groups", json={"name": "семья"}, headers=crm_auth).status_code == 409

    def test_update(self, crm_client, crm_auth):
        group = make_group(crm_client, crm_auth, "Семья")
        other = make_group(crm_client, crm_auth, "Бег")

        resp = crm_client.patch(f"/api/groups/{group['id']}", json={"name": "Родные", "emoji": "🏠"}, headers=crm_auth)

        assert resp.status_code == 200
        assert (resp.json()["name"], resp.json()["emoji"]) == ("Родные", "🏠")
        clash = crm_client.patch(f"/api/groups/{other['id']}", json={"name": "родные"}, headers=crm_auth)
        assert clash.status_code == 409

    def test_rename_to_same_name_is_not_a_conflict(self, crm_client, crm_auth):
        group = make_group(crm_client, crm_auth, "Семья")

        resp = crm_client.patch(f"/api/groups/{group['id']}", json={"name": "Семья", "color": "red"}, headers=crm_auth)

        assert resp.status_code == 200 and resp.json()["color"] == "red"

    def test_empty_patch_returns_group(self, crm_client, crm_auth):
        group = make_group(crm_client, crm_auth, "Семья")

        assert crm_client.patch(f"/api/groups/{group['id']}", json={}, headers=crm_auth).json()["name"] == "Семья"

    def test_update_missing_is_404(self, crm_client, crm_auth):
        for gid in ("64b000000000000000000000", "не-id"):
            resp = crm_client.patch(f"/api/groups/{gid}", json={"emoji": "x"}, headers=crm_auth)
            assert resp.status_code == 404

    def test_delete_removes_group_from_contacts(self, crm_client, crm_auth):
        keep = make_group(crm_client, crm_auth, "Бег")
        gone = make_group(crm_client, crm_auth, "Семья")
        contact = make_contact(crm_client, crm_auth, group_ids=[gone["id"], keep["id"]])

        assert crm_client.delete(f"/api/groups/{gone['id']}", headers=crm_auth).status_code == 204

        fetched = crm_client.get(f"/api/contacts/{contact['id']}", headers=crm_auth).json()
        assert fetched["group_ids"] == [keep["id"]]
        assert [g["name"] for g in crm_client.get("/api/groups", headers=crm_auth).json()] == ["Бег"]

    def test_delete_missing_is_404(self, crm_client, crm_auth):
        assert crm_client.delete("/api/groups/64b000000000000000000000", headers=crm_auth).status_code == 404
        assert crm_client.delete("/api/groups/плохой", headers=crm_auth).status_code == 404

    def test_groups_are_per_user(self, crm_client, crm_auth):
        make_group(crm_client, crm_auth, "Семья")
        resp = crm_client.post("/api/auth/register", json={"email": "boris@example.com", "password": "password-123"})
        boris = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        assert crm_client.get("/api/groups", headers=boris).json() == []

    def test_requires_auth(self, crm_client):
        assert crm_client.get("/api/groups").status_code == 401
