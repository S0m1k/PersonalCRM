"""
Настройки: /api/preferences/priority-labels — названия уровней Priority Map.
"""

from __future__ import annotations

FULL = {"top": "Ближний круг", "high": "Важные", "medium": "Знакомые", "low": "Редко", "none": "Нет"}


def test_defaults(crm_client, crm_auth):
    resp = crm_client.get("/api/preferences/priority-labels", headers=crm_auth)

    assert resp.status_code == 200
    assert resp.json() == {"top": "Топ", "high": "Высокий", "medium": "Средний", "low": "Низкий", "none": "Нет"}


def test_put_then_get(crm_client, crm_auth):
    put = crm_client.put("/api/preferences/priority-labels", json=FULL, headers=crm_auth)
    got = crm_client.get("/api/preferences/priority-labels", headers=crm_auth)

    assert put.status_code == 200 and put.json() == FULL
    assert got.json() == FULL


def test_strips_and_empty_resets_to_default(crm_client, crm_auth):
    crm_client.put("/api/preferences/priority-labels", json={**FULL, "top": "  Семья  ", "low": "  "}, headers=crm_auth)

    got = crm_client.get("/api/preferences/priority-labels", headers=crm_auth).json()

    assert got["top"] == "Семья" and got["low"] == "Низкий"


def test_rejects_long_label(crm_client, crm_auth):
    resp = crm_client.put("/api/preferences/priority-labels", json={**FULL, "top": "я" * 25}, headers=crm_auth)

    assert resp.status_code == 422


def test_accepts_24_chars(crm_client, crm_auth):
    resp = crm_client.put("/api/preferences/priority-labels", json={**FULL, "top": "я" * 24}, headers=crm_auth)

    assert resp.status_code == 200


def test_requires_all_keys_and_no_extras(crm_client, crm_auth):
    missing = {k: v for k, v in FULL.items() if k != "low"}

    assert crm_client.put("/api/preferences/priority-labels", json=missing, headers=crm_auth).status_code == 422
    assert crm_client.put("/api/preferences/priority-labels", json={**FULL, "extra": "x"}, headers=crm_auth).status_code == 422


def test_requires_auth(crm_client):
    assert crm_client.get("/api/preferences/priority-labels").status_code == 401
    assert crm_client.put("/api/preferences/priority-labels", json=FULL).status_code == 401


def test_per_user(crm_client, crm_auth):
    crm_client.put("/api/preferences/priority-labels", json=FULL, headers=crm_auth)
    other = crm_client.post("/api/auth/register", json={"email": "bob@example.com", "password": "password-123"}).json()

    got = crm_client.get(
        "/api/preferences/priority-labels", headers={"Authorization": f"Bearer {other['access_token']}"}
    )

    assert got.json()["top"] == "Топ"
