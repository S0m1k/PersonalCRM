"""
Тесты authorize URL: запрошенных прав должно хватать для двусторонней синхронизации.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.sync import oauth


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(oauth.settings, "ms_client_id", "ms-id")
    monkeypatch.setattr(oauth.settings, "ms_client_secret", "ms-secret")
    monkeypatch.setattr(oauth.settings, "google_client_id", "g-id")
    monkeypatch.setattr(oauth.settings, "google_client_secret", "g-secret")


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_microsoft_scopes_allow_writing_contacts(configured):
    scopes = _query(oauth.ms_authorize_url("s"))["scope"][0].split()

    assert "Contacts.ReadWrite" in scopes
    assert "offline_access" in scopes


def test_microsoft_url_carries_state(configured):
    assert _query(oauth.ms_authorize_url("abc"))["state"] == ["abc"]


def test_google_scope_allows_writing_contacts(configured):
    query = _query(oauth.google_authorize_url("s"))

    assert "https://www.googleapis.com/auth/contacts" in query["scope"][0].split()
    assert query["access_type"] == ["offline"]
