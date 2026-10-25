"""
Календарь без HTTP: права OAuth, маппинг событий провайдеров, блок вопросов в описании.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from app.sync import oauth
from app.sync.calendar_common import QUESTIONS_MARKER, html_to_text, strip_questions_block, with_questions_block
from app.sync.calendar_google import map_google_event
from app.sync.calendar_microsoft import map_graph_event


@pytest.fixture
def configured(monkeypatch):
    for name, value in (
        ("ms_client_id", "ms-id"),
        ("ms_client_secret", "ms-secret"),
        ("google_client_id", "g-id"),
        ("google_client_secret", "g-secret"),
    ):
        monkeypatch.setattr(oauth.settings, name, value)


def test_authorize_urls_request_calendar(configured):
    ms = parse_qs(urlparse(oauth.ms_authorize_url("s")).query)
    google = parse_qs(urlparse(oauth.google_authorize_url("s")).query)

    assert "Calendars.ReadWrite" in ms["scope"][0].split()
    assert "https://www.googleapis.com/auth/calendar.events" in google["scope"][0].split()
    assert google["include_granted_scopes"] == ["true"]


@pytest.mark.parametrize(
    ("provider", "scopes", "expected"),
    [
        ("microsoft", None, False),
        ("microsoft", "Contacts.ReadWrite User.Read", False),
        ("microsoft", "https://graph.microsoft.com/Calendars.ReadWrite openid", True),
        ("google", "https://www.googleapis.com/auth/contacts", False),
        ("google", "https://www.googleapis.com/auth/contacts https://www.googleapis.com/auth/calendar.events", True),
    ],
)
def test_calendar_scope_granted(provider, scopes, expected):
    assert oauth.calendar_scope_granted(provider, scopes) is expected


def test_ms_refresh_never_asks_more_than_granted():
    # Старое подключение: права неизвестны — просим как до Sprint 7, иначе Microsoft откажет
    assert "Calendars" not in oauth._ms_refresh_scopes(None)
    assert oauth._ms_refresh_scopes("Contacts.ReadWrite User.Read openid") == (
        "Contacts.ReadWrite User.Read offline_access"
    )
    assert "Calendars.ReadWrite" in oauth._ms_refresh_scopes("Calendars.ReadWrite Contacts.ReadWrite")


def test_questions_block_roundtrip():
    with_block = with_questions_block("Повестка", [("Петя", "Как отпуск?"), ("", "Без имени")])

    assert with_block == f"Повестка\n\n{QUESTIONS_MARKER}\n• Петя: Как отпуск?\n• Без имени"
    assert strip_questions_block(with_block) == "Повестка"
    # Повторная запись не дублирует блок
    assert with_questions_block(with_block, [("Петя", "Новый")]).count(QUESTIONS_MARKER) == 1
    assert with_questions_block(with_block, []) == "Повестка"


def test_html_to_text():
    assert html_to_text("<html><style>p{}</style><p>Раз</p><p>Два&amp;три</p></html>") == "Раз\nДва&три"
    assert html_to_text("просто текст ") == "просто текст"


def test_graph_all_day_event_and_questions_block_stripped():
    mapped = map_graph_event(
        {
            "id": "1",
            "subject": "Отпуск",
            "isAllDay": True,
            "start": {"dateTime": "2026-11-05T00:00:00.0000000"},
            "end": {"dateTime": "2026-11-07T00:00:00.0000000"},
            "originalStartTimeZone": "Russian Standard Time",  # не IANA
            "body": {"contentType": "text", "content": f"Текст\n\n{QUESTIONS_MARKER}\n• старое"},
        }
    )

    assert mapped["all_day"] is True
    assert (mapped["start"].day, mapped["end"].day) == (5, 7)
    assert mapped["timezone"] == "UTC"
    assert mapped["description"] == "Текст"


def test_google_organizer_counts_as_attendee_unless_self():
    mapped = map_google_event(
        {
            "id": "g",
            "start": {"dateTime": "2026-11-03T12:00:00Z"},
            "end": {"dateTime": "2026-11-03T13:00:00Z"},
            "organizer": {"email": "boss@example.com", "displayName": "Босс"},
            "attendees": [{"email": "BOSS@example.com"}, {"email": "room@x", "resource": True}],
        }
    )

    assert mapped["title"] == "(без названия)"
    assert [(a["email"], a["response"]) for a in mapped["attendees"]] == [("boss@example.com", "organizer")]
