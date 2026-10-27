"""
CalDAV: события CRM как календарь iPhone / Android (DAVx⁵). Те же логин и пароль для телефона, что у CardDAV.

Диалог клиента: discovery (calendar-home-set) → список с ETag → calendar-query / multiget → GET / PUT / DELETE.
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app

NS = {
    "d": "DAV:",
    "c": "urn:ietf:params:xml:ns:caldav",
    "card": "urn:ietf:params:xml:ns:carddav",
    "cs": "http://calendarserver.org/ns/",
}
CAL = "/dav/calendars/events/"
EVENTS = "/api/calendar/events"


def _basic(login: str, password: str) -> dict:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["test_caldav"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def jwt(client) -> dict:
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def dav(client, jwt) -> dict:
    resp = client.post("/api/auth/carddav-password", headers=jwt)
    return _basic("admin", resp.json()["password"])


def _propfind(client, path, headers, depth="0", body=None):
    return client.request(
        "PROPFIND", path, headers={**headers, "Depth": depth, "Content-Type": "application/xml"}, content=body or ""
    )


def _report(client, headers, body, path=CAL):
    return client.request("REPORT", path, headers={**headers, "Depth": "1", "Content-Type": "application/xml"}, content=body)


def _xml(resp) -> ET.Element:
    assert resp.status_code == 207, resp.text
    return ET.fromstring(resp.content)


def _create(client, jwt, **data) -> dict:
    body = {"title": "Встреча с Петром", "start": "2026-11-03T10:00:00", "timezone": "Europe/Moscow", **data}
    resp = client.post(EVENTS, json=body, headers=jwt)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _tenant_db(client):
    """База пользователя admin — для случаев, которые не создать через API (событие провайдера, корзина)."""
    system = app.dependency_overrides[get_db]()
    user = client.portal.call(system["users"].find_one, {})
    return system.client[user["db_name"]]


PHONE_EVENT = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iOS 18//EN\r\n"
    "BEGIN:VEVENT\r\nUID:PHONE-EV-1\r\nSUMMARY:Стоматолог\r\n"
    "DTSTART;TZID=Europe/Moscow:20261105T153000\r\nDTEND;TZID=Europe/Moscow:20261105T163000\r\n"
    "LOCATION:Клиника\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
)
RECURRING_EVENT = (
    "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Apple Inc.//iOS 18//EN\r\n"
    "BEGIN:VTIMEZONE\r\nTZID:Europe/Moscow\r\nBEGIN:STANDARD\r\nDTSTART:19700101T000000\r\n"
    "TZOFFSETFROM:+0300\r\nTZOFFSETTO:+0300\r\nEND:STANDARD\r\nEND:VTIMEZONE\r\n"
    "BEGIN:VEVENT\r\nUID:PHONE-EV-2\r\nSUMMARY:Планёрка\r\n"
    "DTSTART;TZID=Europe/Moscow:20261103T100000\r\nDTEND;TZID=Europe/Moscow:20261103T103000\r\n"
    "RRULE:FREQ=WEEKLY;BYDAY=TU\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\n"
    "END:VEVENT\r\nEND:VCALENDAR\r\n"
)


class TestAccess:
    def test_requires_basic_auth(self, client):
        assert _propfind(client, CAL, {}).status_code == 401

    def test_wrong_password_is_rejected(self, client, dav):
        assert _propfind(client, CAL, _basic("admin", "nope")).status_code == 401

    def test_well_known_caldav_redirects_to_dav_root(self, client):
        resp = client.request("PROPFIND", "/.well-known/caldav", follow_redirects=False)

        assert resp.status_code in (301, 308)
        assert resp.headers["location"].endswith("/dav/")

    def test_options_announces_calendar_access(self, client, dav):
        resp = client.options(CAL, headers=dav)

        assert "calendar-access" in resp.headers["DAV"]


class TestDiscovery:
    def test_principal_has_calendar_home(self, client, dav):
        body = (
            '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
            "<c:calendar-home-set/><d:current-user-principal/></d:prop></d:propfind>"
        )

        root = _xml(_propfind(client, "/dav/principal/", dav, body=body))

        assert root.find(".//c:calendar-home-set/d:href", NS).text == "/dav/calendars/"

    def test_home_lists_calendar(self, client, dav):
        root = _xml(_propfind(client, "/dav/calendars/", dav, depth="1"))

        hrefs = [h.text for h in root.findall("d:response/d:href", NS)]
        assert CAL in hrefs
        cal = next(r for r in root.findall("d:response", NS) if r.find("d:href", NS).text == CAL)
        assert cal.find(".//d:resourcetype/c:calendar", NS) is not None
        assert cal.find(".//d:displayname", NS).text == "PersonalCRM"

    def test_calendar_supports_events_and_reports(self, client, dav):
        body = (
            '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
            "<c:supported-calendar-component-set/><d:supported-report-set/></d:prop></d:propfind>"
        )

        root = _xml(_propfind(client, CAL, dav, body=body))

        comp = root.find(".//c:supported-calendar-component-set/c:comp", NS)
        assert comp.get("name") == "VEVENT"
        reports = {el.tag for el in root.findall(".//d:supported-report/d:report/*", NS)}
        assert f"{{{NS['c']}}}calendar-query" in reports
        assert f"{{{NS['c']}}}calendar-multiget" in reports

    def test_contacts_discovery_still_works(self, client, dav):
        body = '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><card:addressbook-home-set/></d:prop></d:propfind>'

        root = _xml(_propfind(client, "/dav/principal/", dav, body=body))

        assert root.find(".//card:addressbook-home-set/d:href", NS).text == "/dav/addressbooks/"


class TestListing:
    def test_events_listed_with_etags(self, client, dav, jwt):
        event = _create(client, jwt)

        root = _xml(_propfind(client, CAL, dav, depth="1"))

        items = [r for r in root.findall("d:response", NS) if r.find("d:href", NS).text != CAL]
        assert [i.find("d:href", NS).text for i in items] == [f"{CAL}{event['id']}.ics"]
        assert items[0].find(".//d:getetag", NS).text.startswith('"')

    def test_ctag_changes_when_event_changes(self, client, dav, jwt):
        event = _create(client, jwt)
        ctag = lambda: _xml(_propfind(client, CAL, dav)).find(".//cs:getctag", NS).text  # noqa: E731
        before = ctag()

        client.patch(f"{EVENTS}/{event['id']}", json={"title": "Новое название"}, headers=jwt)

        assert ctag() != before

    def test_time_range_query_filters_events(self, client, dav, jwt):
        inside = _create(client, jwt, title="В ноябре", start="2026-11-10T10:00:00")
        _create(client, jwt, title="В декабре", start="2026-12-10T10:00:00")
        body = (
            '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            "<d:prop><d:getetag/><c:calendar-data/></d:prop>"
            '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
            '<c:time-range start="20261101T000000Z" end="20261201T000000Z"/>'
            "</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>"
        )

        root = _xml(_report(client, dav, body))

        hrefs = [h.text for h in root.findall("d:response/d:href", NS)]
        assert hrefs == [f"{CAL}{inside['id']}.ics"]
        assert "SUMMARY:В ноябре" in root.find(".//c:calendar-data", NS).text

    def test_multiget_returns_calendar_data_and_404_for_missing(self, client, dav, jwt):
        event = _create(client, jwt)
        href = f"{CAL}{event['id']}.ics"
        body = (
            '<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">'
            f"<d:prop><d:getetag/><c:calendar-data/></d:prop><d:href>{href}</d:href><d:href>{CAL}missing.ics</d:href>"
            "</c:calendar-multiget>"
        )

        root = _xml(_report(client, dav, body))

        found = {r.find("d:href", NS).text: r for r in root.findall("d:response", NS)}
        assert "DTSTART:20261103T070000Z" in found[href].find(".//c:calendar-data", NS).text
        assert found[f"{CAL}missing.ics"].find("d:status", NS).text == "HTTP/1.1 404 Not Found"


class TestReadWrite:
    def test_get_ics(self, client, dav, jwt):
        event = _create(client, jwt, location="Офис")

        resp = client.get(f"{CAL}{event['id']}.ics", headers=dav)

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/calendar")
        assert resp.headers["etag"].startswith('"')
        assert "SUMMARY:Встреча с Петром" in resp.text
        assert "LOCATION:Офис" in resp.text

    def test_put_new_event_keeps_client_href_and_uid(self, client, dav, jwt):
        href = f"{CAL}PHONE-EV-1.ics"

        created = client.put(href, headers={**dav, "If-None-Match": "*"}, content=PHONE_EVENT.encode())
        fetched = client.get(href, headers=dav)

        assert created.status_code == 201
        assert created.headers["etag"]
        assert "UID:PHONE-EV-1" in fetched.text
        listed = client.get(EVENTS, headers=jwt).json()
        assert listed[0]["title"] == "Стоматолог"
        assert listed[0]["start"].startswith("2026-11-05T12:30:00")
        assert listed[0]["timezone"] == "Europe/Moscow"
        assert listed[0]["source"] == "crm"

    def test_put_update_keeps_crm_only_data(self, client, dav, jwt):
        contact = client.post("/api/contacts/", json={"first_name": "Пётр"}, headers=jwt).json()
        event = _create(client, jwt, contact_ids=[contact["id"]], push_questions=True)
        href = f"{CAL}{event['id']}.ics"
        etag = client.get(href, headers=dav).headers["etag"]
        card = client.get(href, headers=dav).text.replace("SUMMARY:Встреча с Петром", "SUMMARY:Встреча перенесена")

        resp = client.put(href, headers={**dav, "If-Match": etag}, content=card.encode())

        assert resp.status_code == 204
        updated = client.get(f"{EVENTS}/{event['id']}", headers=jwt).json()
        assert updated["title"] == "Встреча перенесена"
        assert updated["contact_ids"] == [contact["id"]]
        assert updated["push_questions"] is True

    def test_stale_etag_is_412(self, client, dav, jwt):
        event = _create(client, jwt)

        resp = client.put(
            f"{CAL}{event['id']}.ics", headers={**dav, "If-Match": '"stale"'}, content=PHONE_EVENT.encode()
        )

        assert resp.status_code == 412

    def test_create_over_existing_with_if_none_match_is_412(self, client, dav, jwt):
        event = _create(client, jwt)

        resp = client.put(
            f"{CAL}{event['id']}.ics", headers={**dav, "If-None-Match": "*"}, content=PHONE_EVENT.encode()
        )

        assert resp.status_code == 412

    @pytest.mark.parametrize(
        "body",
        [
            "not a calendar",
            "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:X\r\nSUMMARY:Без даты\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n",
            "BEGIN:VCALENDAR\r\nBEGIN:VTODO\r\nUID:T\r\nSUMMARY:Задача\r\nEND:VTODO\r\nEND:VCALENDAR\r\n",
        ],
    )
    def test_invalid_calendar_is_400(self, client, dav, body):
        assert client.put(f"{CAL}x.ics", headers=dav, content=body.encode()).status_code == 400

    def test_unsafe_name_is_404(self, client, dav):
        assert client.put(f"{CAL}..%2Fx.ics", headers=dav, content=PHONE_EVENT.encode()).status_code == 404

    def test_delete_moves_event_to_trash(self, client, dav, jwt):
        event = _create(client, jwt)

        resp = client.delete(f"{CAL}{event['id']}.ics", headers=dav)

        assert resp.status_code == 204
        assert client.get(f"{EVENTS}/{event['id']}", headers=jwt).status_code == 404
        assert client.get(f"{CAL}{event['id']}.ics", headers=dav).status_code == 404
        trashed = client.portal.call(_tenant_db(client)["events_trash"].find_one, {"title": "Встреча с Петром"})
        assert trashed["deleted_via"] == "caldav"


class TestRecurringAndExtras:
    def test_original_ical_is_returned_untouched(self, client, dav):
        href = f"{CAL}PHONE-EV-2.ics"
        client.put(href, headers={**dav, "If-None-Match": "*"}, content=RECURRING_EVENT.encode())

        got = client.get(href, headers=dav)

        assert got.text == RECURRING_EVENT  # VTIMEZONE, RRULE и VALARM — как прислал телефон

    def test_edit_in_crm_keeps_recurrence_and_alarm(self, client, dav, jwt):
        href = f"{CAL}PHONE-EV-2.ics"
        client.put(href, headers={**dav, "If-None-Match": "*"}, content=RECURRING_EVENT.encode())
        event_id = client.get(EVENTS, headers=jwt).json()[0]["id"]

        client.patch(f"{EVENTS}/{event_id}", json={"title": "Планёрка команды"}, headers=jwt)
        got = client.get(href, headers=dav).text

        assert "SUMMARY:Планёрка команды" in got
        assert "RRULE:FREQ=WEEKLY;BYDAY=TU" in got
        assert "BEGIN:VALARM" in got

    def test_etag_changes_after_crm_edit(self, client, dav, jwt):
        href = f"{CAL}PHONE-EV-1.ics"
        created = client.put(href, headers={**dav, "If-None-Match": "*"}, content=PHONE_EVENT.encode())
        event_id = client.get(EVENTS, headers=jwt).json()[0]["id"]

        client.patch(f"{EVENTS}/{event_id}", json={"location": "Другая клиника"}, headers=jwt)

        assert client.get(href, headers=dav).headers["etag"] != created.headers["etag"]


class TestProviderEvents:
    def _provider_event(self, client) -> str:
        db = _tenant_db(client)
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        doc = {
            "title": "Созвон из Outlook",
            "start": datetime(2026, 11, 4, 8, 0, tzinfo=timezone.utc),
            "end": datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc),
            "all_day": False,
            "timezone": "UTC",
            "location": "",
            "description": "",
            "attendees": [],
            "contact_ids": [],
            "source": "microsoft",
            "connection_id": "conn-1",
            "external_id": "AAMk-1",
            "created_at": now,
            "updated_at": now,
        }
        return str(client.portal.call(db["events"].insert_one, doc).inserted_id)

    def test_provider_event_is_readable(self, client, dav):
        event_id = self._provider_event(client)

        resp = client.get(f"{CAL}{event_id}.ics", headers=dav)

        assert resp.status_code == 200
        assert "SUMMARY:Созвон из Outlook" in resp.text

    def test_provider_event_is_read_only_for_put(self, client, dav):
        event_id = self._provider_event(client)
        href = f"{CAL}{event_id}.ics"
        etag = client.get(href, headers=dav).headers["etag"]

        resp = client.put(href, headers={**dav, "If-Match": etag}, content=PHONE_EVENT.encode())

        assert resp.status_code == 403

    def test_provider_event_cannot_be_deleted_from_phone(self, client, dav, jwt):
        event_id = self._provider_event(client)

        resp = client.delete(f"{CAL}{event_id}.ics", headers=dav)

        assert resp.status_code == 403
        assert client.get(f"{EVENTS}/{event_id}", headers=jwt).status_code == 200


class TestRecurringInRange:
    def test_recurring_event_is_returned_for_later_ranges(self, client, dav):
        """Еженедельная встреча начата в ноябре — в запросе на январь телефон должен её получить."""
        client.put(f"{CAL}PHONE-EV-2.ics", headers={**dav, "If-None-Match": "*"}, content=RECURRING_EVENT.encode())
        body = (
            '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/></d:prop>'
            '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
            '<c:time-range start="20270101T000000Z" end="20270201T000000Z"/>'
            "</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>"
        )

        root = _xml(_report(client, dav, body))

        assert [h.text for h in root.findall("d:response/d:href", NS)] == [f"{CAL}PHONE-EV-2.ics"]

    def test_one_off_event_is_not_returned_for_other_ranges(self, client, dav):
        client.put(f"{CAL}PHONE-EV-1.ics", headers={**dav, "If-None-Match": "*"}, content=PHONE_EVENT.encode())
        body = (
            '<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:getetag/></d:prop>'
            '<c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">'
            '<c:time-range start="20270101T000000Z" end="20270201T000000Z"/>'
            "</c:comp-filter></c:comp-filter></c:filter></c:calendar-query>"
        )

        assert _xml(_report(client, dav, body)).findall("d:response", NS) == []
