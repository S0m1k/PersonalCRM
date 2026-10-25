"""
API вопросов к человеку: «что хочу спросить» → ответ.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["test_questions"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth(client):
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def contact(client, auth) -> dict:
    return client.post("/api/contacts/", json={"first_name": "Пётр", "last_name": "Иванов"}, headers=auth).json()


def _ask(client, auth, contact_id: str, text: str = "Как прошёл переезд?", **extra) -> dict:
    resp = client.post("/api/questions", json={"contact_id": contact_id, "text": text, **extra}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestCreate:
    def test_new_question_is_open(self, client, auth, contact):
        question = _ask(client, auth, contact["id"])

        assert question["status"] == "open"
        assert question["contact_id"] == contact["id"]
        assert question["answer"] == ""
        assert question["source"] == "manual"

    def test_ask_at_next_meeting_or_date(self, client, auth, contact):
        assert _ask(client, auth, contact["id"], ask_at="next_meeting")["ask_at"] == "next_meeting"
        assert _ask(client, auth, contact["id"], ask_at="2026-11-01")["ask_at"] == "2026-11-01"

    def test_invalid_ask_at_is_rejected(self, client, auth, contact):
        resp = client.post(
            "/api/questions",
            json={"contact_id": contact["id"], "text": "?", "ask_at": "завтра"},
            headers=auth,
        )
        assert resp.status_code == 422

    def test_empty_text_is_rejected(self, client, auth, contact):
        resp = client.post("/api/questions", json={"contact_id": contact["id"], "text": "  "}, headers=auth)
        assert resp.status_code == 422

    def test_unknown_contact_is_404(self, client, auth):
        resp = client.post(
            "/api/questions", json={"contact_id": "000000000000000000000000", "text": "?"}, headers=auth
        )
        assert resp.status_code == 404

    def test_requires_auth(self, client, contact):
        assert client.post("/api/questions", json={"contact_id": contact["id"], "text": "?"}).status_code == 401


class TestLifecycle:
    def test_answering_sets_answer_and_time(self, client, auth, contact):
        question = _ask(client, auth, contact["id"])

        resp = client.patch(
            f"/api/questions/{question['id']}",
            json={"status": "answered", "answer": "Отлично, уже в Дубае"},
            headers=auth,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "answered"
        assert resp.json()["answer"] == "Отлично, уже в Дубае"
        assert resp.json()["answered_at"] is not None

    def test_reopening_clears_answered_at(self, client, auth, contact):
        question = _ask(client, auth, contact["id"])
        client.patch(f"/api/questions/{question['id']}", json={"status": "answered", "answer": "Да"}, headers=auth)

        reopened = client.patch(f"/api/questions/{question['id']}", json={"status": "open"}, headers=auth).json()

        assert reopened["status"] == "open"
        assert reopened["answered_at"] is None

    def test_drop_and_delete(self, client, auth, contact):
        question = _ask(client, auth, contact["id"])

        dropped = client.patch(f"/api/questions/{question['id']}", json={"status": "dropped"}, headers=auth)
        deleted = client.delete(f"/api/questions/{question['id']}", headers=auth)

        assert dropped.json()["status"] == "dropped"
        assert deleted.status_code == 204
        assert client.patch(f"/api/questions/{question['id']}", json={"text": "x"}, headers=auth).status_code == 404

    def test_questions_are_deleted_with_contact(self, client, auth, contact):
        _ask(client, auth, contact["id"])

        client.delete(f"/api/contacts/{contact['id']}", headers=auth)

        assert client.get("/api/questions", headers=auth).json() == []


class TestList:
    def test_filter_by_status_and_contact(self, client, auth, contact):
        other = client.post("/api/contacts/", json={"first_name": "Марина"}, headers=auth).json()
        q1 = _ask(client, auth, contact["id"], "Первый")
        _ask(client, auth, contact["id"], "Второй")
        _ask(client, auth, other["id"], "Третий")
        client.patch(f"/api/questions/{q1['id']}", json={"status": "answered", "answer": "ok"}, headers=auth)

        open_for_petr = client.get(
            "/api/questions", params={"status": "open", "contact_id": contact["id"]}, headers=auth
        ).json()

        assert [q["text"] for q in open_for_petr] == ["Второй"]

    def test_list_includes_contact_name(self, client, auth, contact):
        _ask(client, auth, contact["id"])

        listed = client.get("/api/questions", headers=auth).json()

        assert listed[0]["contact_name"] == "Пётр Иванов"

    def test_open_counts_per_contact(self, client, auth, contact):
        _ask(client, auth, contact["id"], "Один")
        _ask(client, auth, contact["id"], "Два")

        counts = client.get("/api/questions/open-counts", headers=auth).json()

        assert counts == {contact["id"]: 2}
