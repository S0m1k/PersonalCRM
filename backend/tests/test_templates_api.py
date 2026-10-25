"""
API шаблонов карточек и привязка типизированных полей к контакту.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["test_templates"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_template(client, auth, **overrides) -> dict:
    body = {
        "name": "Инвестор",
        "icon": "coins",
        "fields": [
            {"label": "Фонд", "type": "text"},
            {"label": "Чек", "type": "number"},
            {"label": "Стадия", "type": "select", "options": ["Seed", "A"]},
        ],
    }
    body.update(overrides)
    resp = client.post("/api/templates", json=body, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestDefaults:
    def test_first_list_returns_builtin_templates(self, client, auth):
        names = [t["name"] for t in client.get("/api/templates", headers=auth).json()]

        assert names == ["Клиент", "Партнёр", "Друг", "Родственник", "Сотрудник"]

    def test_defaults_are_seeded_only_once(self, client, auth):
        client.get("/api/templates", headers=auth)
        again = client.get("/api/templates", headers=auth).json()

        assert len(again) == 5

    def test_builtin_templates_have_fields_with_keys(self, client, auth):
        for template in client.get("/api/templates", headers=auth).json():
            assert template["fields"], template["name"]
            assert all(f["key"] for f in template["fields"])

    def test_requires_auth(self, client):
        assert client.get("/api/templates").status_code == 401


class TestCrud:
    def test_create_assigns_unique_field_keys(self, client, auth):
        template = _create_template(client, auth)

        keys = [f["key"] for f in template["fields"]]
        assert len(set(keys)) == 3
        assert all(keys)

    def test_select_without_options_is_rejected(self, client, auth):
        resp = client.post(
            "/api/templates",
            json={"name": "X", "fields": [{"label": "Стадия", "type": "select"}]},
            headers=auth,
        )
        assert resp.status_code == 422

    def test_duplicate_explicit_keys_are_rejected(self, client, auth):
        resp = client.post(
            "/api/templates",
            json={
                "name": "X",
                "fields": [
                    {"key": "a", "label": "A", "type": "text"},
                    {"key": "a", "label": "B", "type": "text"},
                ],
            },
            headers=auth,
        )
        assert resp.status_code == 422

    def test_update_keeps_existing_keys(self, client, auth):
        template = _create_template(client, auth)
        fields = template["fields"]
        fields[0]["label"] = "Название фонда"

        resp = client.patch(
            f"/api/templates/{template['id']}",
            json={"name": "Инвестор VC", "fields": fields + [{"label": "Сайт", "type": "url"}]},
            headers=auth,
        )

        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["name"] == "Инвестор VC"
        assert updated["fields"][0] == {**fields[0], "label": "Название фонда"}
        assert len(updated["fields"]) == 4

    def test_delete_unused_template(self, client, auth):
        template = _create_template(client, auth)

        assert client.delete(f"/api/templates/{template['id']}", headers=auth).status_code == 204
        assert client.get(f"/api/templates/{template['id']}", headers=auth).status_code == 404

    def test_delete_template_in_use_is_conflict(self, client, auth):
        template = _create_template(client, auth)
        client.post("/api/contacts/", json={"first_name": "A", "template_id": template["id"]}, headers=auth)

        assert client.delete(f"/api/templates/{template['id']}", headers=auth).status_code == 409


class TestContactFields:
    def test_contact_fields_are_validated_and_normalized(self, client, auth):
        template = _create_template(client, auth)
        keys = {f["label"]: f["key"] for f in template["fields"]}

        resp = client.post(
            "/api/contacts/",
            json={
                "first_name": "Олег",
                "template_id": template["id"],
                "fields": {keys["Фонд"]: " Север ", keys["Чек"]: "250000", keys["Стадия"]: "Seed"},
            },
            headers=auth,
        )

        assert resp.status_code == 201, resp.text
        assert resp.json()["template_id"] == template["id"]
        assert resp.json()["fields"] == {keys["Фонд"]: "Север", keys["Чек"]: 250000, keys["Стадия"]: "Seed"}

    def test_invalid_field_value_is_422_with_label(self, client, auth):
        template = _create_template(client, auth)
        stage_key = template["fields"][2]["key"]

        resp = client.post(
            "/api/contacts/",
            json={"first_name": "Олег", "template_id": template["id"], "fields": {stage_key: "Series Z"}},
            headers=auth,
        )

        assert resp.status_code == 422
        assert "Стадия" in resp.text

    def test_unknown_template_is_422(self, client, auth):
        resp = client.post(
            "/api/contacts/",
            json={"first_name": "Олег", "template_id": "000000000000000000000000"},
            headers=auth,
        )
        assert resp.status_code == 422

    def test_patch_fields_validated_against_existing_template(self, client, auth):
        template = _create_template(client, auth)
        cheque_key = template["fields"][1]["key"]
        contact = client.post(
            "/api/contacts/", json={"first_name": "Олег", "template_id": template["id"]}, headers=auth
        ).json()

        bad = client.patch(f"/api/contacts/{contact['id']}", json={"fields": {cheque_key: "много"}}, headers=auth)
        good = client.patch(f"/api/contacts/{contact['id']}", json={"fields": {cheque_key: "10"}}, headers=auth)

        assert bad.status_code == 422
        assert good.status_code == 200
        assert good.json()["fields"] == {cheque_key: 10}

    def test_contacts_can_be_filtered_by_template(self, client, auth):
        template = _create_template(client, auth)
        client.post("/api/contacts/", json={"first_name": "С шаблоном", "template_id": template["id"]}, headers=auth)
        client.post("/api/contacts/", json={"first_name": "Без шаблона"}, headers=auth)

        listed = client.get("/api/contacts/", params={"template_id": template["id"]}, headers=auth).json()

        assert [c["first_name"] for c in listed] == ["С шаблоном"]

    def test_template_can_be_cleared(self, client, auth):
        template = _create_template(client, auth)
        contact = client.post(
            "/api/contacts/", json={"first_name": "Олег", "template_id": template["id"]}, headers=auth
        ).json()

        resp = client.patch(f"/api/contacts/{contact['id']}", json={"template_id": ""}, headers=auth)

        assert resp.status_code == 200
        assert resp.json()["template_id"] is None


class TestIcons:
    def test_builtin_icons_are_svg_names(self, client, auth):
        from app.models.template import TEMPLATE_ICONS

        icons = [t["icon"] for t in client.get("/api/templates", headers=auth).json()]

        assert icons == ["briefcase", "handshake", "smile", "house", "id-card"]
        assert set(icons) <= set(TEMPLATE_ICONS)

    def test_unknown_icon_is_rejected(self, client, auth):
        resp = client.post("/api/templates", json={"name": "X", "icon": "💰", "fields": []}, headers=auth)

        assert resp.status_code == 422

    def test_default_icon(self, client, auth):
        resp = client.post("/api/templates", json={"name": "X", "fields": []}, headers=auth)

        assert resp.json()["icon"] == "file-text"


def test_legacy_emoji_icons_are_read_as_svg_names():
    """В базе уже лежат шаблоны с эмодзи — при чтении они становятся именами иконок."""
    from datetime import datetime, timezone

    from bson import ObjectId

    from app.models.template import TemplateOut

    now = datetime.now(timezone.utc)
    base = {"name": "Клиент", "fields": [], "created_at": now, "updated_at": now}

    assert TemplateOut.from_mongo({**base, "_id": ObjectId(), "icon": "💼"}).icon == "briefcase"
    assert TemplateOut.from_mongo({**base, "_id": ObjectId(), "icon": "🧑‍💼"}).icon == "id-card"
    assert TemplateOut.from_mongo({**base, "_id": ObjectId(), "icon": "🦄"}).icon == "file-text"
