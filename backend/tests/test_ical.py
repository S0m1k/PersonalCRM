"""
iCalendar (RFC 5545) для CalDAV: событие CRM ↔ VEVENT iPhone / Android.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.event import EventOut
from app.services.ical import IcalError, event_to_ical, ical_to_fields, ical_uid

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=timezone.utc)


def _event(**overrides) -> EventOut:
    data = {
        "id": "6ad7dc44345abcdd100168a2",
        "title": "Встреча с Петром",
        "start": datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc),
        "timezone": "Europe/Moscow",
        "location": "Офис «Альфа», Москва",
        "description": "Обсудить; сроки, бюджет\nВторая строка",
        "attendees": [{"email": "petr@alfa.ru", "name": "Пётр Иванов", "response": "accepted"}],
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(overrides)
    return EventOut(**data)


def _wrap(body: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n" + body + "END:VCALENDAR\r\n"


class TestWrite:
    def test_timed_event_is_utc(self):
        ics = event_to_ical(_event())

        assert ics.startswith("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n")
        assert ics.endswith("END:VCALENDAR\r\n")
        assert "UID:6ad7dc44345abcdd100168a2\r\n" in ics
        assert "SUMMARY:Встреча с Петром\r\n" in ics
        assert "DTSTART:20261103T070000Z\r\n" in ics
        assert "DTEND:20261103T083000Z\r\n" in ics
        assert "DTSTAMP:" in ics
        assert "LAST-MODIFIED:20261027T090000Z\r\n" in ics

    def test_all_day_event_uses_dates(self):
        ics = event_to_ical(
            _event(all_day=True, start=datetime(2026, 11, 3, tzinfo=timezone.utc), end=datetime(2026, 11, 5, tzinfo=timezone.utc))
        )

        assert "DTSTART;VALUE=DATE:20261103\r\n" in ics
        assert "DTEND;VALUE=DATE:20261105\r\n" in ics

    def test_text_is_escaped_and_attendee_written(self):
        ics = event_to_ical(_event()).replace("\r\n ", "")

        assert "LOCATION:Офис «Альфа"  in ics
        assert "\\, Москва" in ics
        assert "DESCRIPTION:Обсудить\\; сроки\\, бюджет\\nВторая строка" in ics
        assert "ATTENDEE;CN=Пётр Иванов;PARTSTAT=ACCEPTED:mailto:petr@alfa.ru" in ics

    def test_long_lines_are_folded(self):
        ics = event_to_ical(_event(description="ж" * 300))

        assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))

    def test_client_uid_is_kept(self):
        assert "UID:PHONE-1\r\n" in event_to_ical(_event(), uid="PHONE-1")

    def test_roundtrip(self):
        fields = ical_to_fields(event_to_ical(_event()))

        assert fields["title"] == "Встреча с Петром"
        assert fields["start"] == datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc)
        assert fields["end"] == datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc)
        assert fields["all_day"] is False
        assert fields["location"] == "Офис «Альфа», Москва"
        assert fields["description"] == "Обсудить; сроки, бюджет\nВторая строка"
        assert fields["attendees"] == [{"email": "petr@alfa.ru", "name": "Пётр Иванов", "phone": "", "response": "accepted"}]


class TestRead:
    def test_tzid_is_converted_to_utc(self):
        ics = _wrap(
            "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:Звонок\r\n"
            "DTSTART;TZID=Europe/Moscow:20261103T100000\r\nDTEND;TZID=Europe/Moscow:20261103T104500\r\nEND:VEVENT\r\n"
        )

        fields = ical_to_fields(ics)

        assert fields["start"] == datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc)
        assert fields["end"] == datetime(2026, 11, 3, 7, 45, tzinfo=timezone.utc)
        assert fields["timezone"] == "Europe/Moscow"

    def test_vtimezone_block_is_ignored_when_tzid_is_iana(self):
        ics = _wrap(
            "BEGIN:VTIMEZONE\r\nTZID:Europe/Moscow\r\nBEGIN:STANDARD\r\nDTSTART:19700101T000000\r\n"
            "TZOFFSETFROM:+0300\r\nTZOFFSETTO:+0300\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n"
            "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:X\r\nDTSTART;TZID=Europe/Moscow:20261103T100000\r\nEND:VEVENT\r\n"
        )

        assert ical_to_fields(ics)["start"] == datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc)

    def test_all_day_without_end_is_one_day(self):
        ics = _wrap("BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:ДР\r\nDTSTART;VALUE=DATE:20261103\r\nEND:VEVENT\r\n")

        fields = ical_to_fields(ics)

        assert fields["all_day"] is True
        assert fields["start"] == datetime(2026, 11, 3, tzinfo=timezone.utc)
        assert fields["end"] == datetime(2026, 11, 4, tzinfo=timezone.utc)

    def test_duration_instead_of_end(self):
        ics = _wrap("BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:X\r\nDTSTART:20261103T070000Z\r\nDURATION:PT1H30M\r\nEND:VEVENT\r\n")

        assert ical_to_fields(ics)["end"] == datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc)

    def test_floating_time_is_taken_as_utc(self):
        ics = _wrap("BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:X\r\nDTSTART:20261103T100000\r\nEND:VEVENT\r\n")

        fields = ical_to_fields(ics)

        assert fields["start"] == datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

    def test_missing_title_gets_placeholder(self):
        ics = _wrap("BEGIN:VEVENT\r\nUID:A1\r\nDTSTART:20261103T070000Z\r\nEND:VEVENT\r\n")

        assert ical_to_fields(ics)["title"] == "Без названия"

    def test_organizer_alarm_and_rrule_are_preserved_as_extras(self):
        ics = _wrap(
            "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:Планёрка\r\nDTSTART:20261103T070000Z\r\nDTEND:20261103T073000Z\r\n"
            "RRULE:FREQ=WEEKLY;BYDAY=TU\r\nORGANIZER;CN=Я:mailto:me@x.ru\r\n"
            "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT\r\n"
        )

        extras = ical_to_fields(ics)["dav_extra"]

        assert "RRULE:FREQ=WEEKLY;BYDAY=TU" in extras
        assert "ORGANIZER;CN=Я:mailto:me@x.ru" in extras
        assert "BEGIN:VALARM" in extras and "TRIGGER:-PT15M" in extras and "END:VALARM" in extras

    def test_extras_are_written_back(self):
        fields = ical_to_fields(
            _wrap(
                "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:Планёрка\r\nDTSTART:20261103T070000Z\r\nRRULE:FREQ=WEEKLY\r\n"
                "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT\r\n"
            )
        )

        ics = event_to_ical(_event(), extra=fields["dav_extra"])

        assert "RRULE:FREQ=WEEKLY\r\n" in ics
        assert "BEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\n" in ics

    def test_folded_lines(self):
        ics = _wrap("BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:Длинное \r\n название\r\nDTSTART:20261103T070000Z\r\nEND:VEVENT\r\n")

        assert ical_to_fields(ics)["title"] == "Длинное название"

    def test_uid(self):
        assert ical_uid(_wrap("BEGIN:VEVENT\r\nUID:XYZ-1\r\nDTSTART:20261103T070000Z\r\nEND:VEVENT\r\n")) == "XYZ-1"

    @pytest.mark.parametrize(
        "body",
        [
            "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:X\r\nEND:VEVENT\r\n",  # нет DTSTART
            "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:X\r\nDTSTART;TZID=Mars/Olympus:20261103T100000\r\nEND:VEVENT\r\n",
            "BEGIN:VEVENT\r\nUID:A1\r\nSUMMARY:X\r\nDTSTART:не дата\r\nEND:VEVENT\r\n",
        ],
    )
    def test_invalid_events_raise(self, body):
        with pytest.raises(IcalError):
            ical_to_fields(_wrap(body))

    def test_calendar_without_event_raises(self):
        with pytest.raises(IcalError):
            ical_to_fields(_wrap("BEGIN:VTODO\r\nUID:T1\r\nSUMMARY:Задача\r\nEND:VTODO\r\n"))
