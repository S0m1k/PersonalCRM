"""
CardDAV: контакты CRM как адресная книга iPhone / Android (DAVx⁵).

Проверяем ровно тот диалог, который ведут клиенты: discovery → список с ETag →
multiget → GET / PUT / DELETE. Вход — email пользователя + пароль для телефона,
выпущенный через /api/auth/carddav-password.
"""

from __future__ import annotations

import base64
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.db import get_db
from app.main import app

NS = {"d": "DAV:", "card": "urn:ietf:params:xml:ns:carddav", "cs": "http://calendarserver.org/ns/"}
BOOK = "/dav/addressbooks/contacts/"


def _basic(login: str, password: str) -> dict:
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def client():
    db = AsyncMongoMockClient()["test_carddav"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def jwt(client) -> dict:
    resp = client.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def dav_password(client, jwt) -> str:
    resp = client.post("/api/auth/carddav-password", headers=jwt)
    assert resp.status_code == 200
    assert resp.json()["username"] == "admin"
    return resp.json()["password"]


@pytest.fixture
def dav(dav_password) -> dict:
    return _basic("admin", dav_password)


def _propfind(client, path, headers, depth="0", body=None):
    return client.request(
        "PROPFIND", path, headers={**headers, "Depth": depth, "Content-Type": "application/xml"}, content=body or ""
    )


def _xml(resp) -> ET.Element:
    assert resp.status_code == 207, resp.text
    return ET.fromstring(resp.content)


def _create(client, jwt, **data) -> dict:
    resp = client.post("/api/contacts/", json={"first_name": "Пётр", "last_name": "Иванов", **data}, headers=jwt)
    assert resp.status_code == 201
    return resp.json()


VCARD_FROM_PHONE = (
    "BEGIN:VCARD\r\nVERSION:3.0\r\nN:Козлова;Анна;;;\r\nFN:Анна Козлова\r\n"
    "TEL;type=CELL:+7 921 555-12-12\r\nUID:PHONE-UID-1\r\nEND:VCARD\r\n"
)


class TestAccess:
    def test_revoked_password_stops_working(self, client, jwt, dav):
        assert client.delete("/api/auth/carddav-password", headers=jwt).status_code == 204

        assert _propfind(client, BOOK, dav).status_code == 401

    def test_new_password_replaces_old(self, client, jwt, dav):
        client.post("/api/auth/carddav-password", headers=jwt)

        assert _propfind(client, BOOK, dav).status_code == 401

    def test_requires_basic_auth(self, client):
        resp = _propfind(client, BOOK, {})

        assert resp.status_code == 401
        assert resp.headers["WWW-Authenticate"].startswith("Basic")

    def test_wrong_password_is_rejected(self, client):
        bad = base64.b64encode(b"admin:nope").decode()

        assert _propfind(client, BOOK, {"Authorization": f"Basic {bad}"}).status_code == 401

    def test_well_known_redirects_to_dav_root(self, client):
        resp = client.request("PROPFIND", "/.well-known/carddav", follow_redirects=False)

        assert resp.status_code in (301, 308)
        assert resp.headers["location"].endswith("/dav/")

    def test_options_announces_addressbook(self, client, dav):
        resp = client.options(BOOK, headers=dav)

        assert "addressbook" in resp.headers["DAV"]


class TestDiscovery:
    def test_principal_and_home(self, client, dav):
        body = (
            '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop>'
            "<d:current-user-principal/><card:addressbook-home-set/></d:prop></d:propfind>"
        )

        root = _xml(_propfind(client, "/dav/", dav, body=body))

        assert root.find(".//d:current-user-principal/d:href", NS).text == "/dav/principal/"
        assert root.find(".//card:addressbook-home-set/d:href", NS).text == "/dav/addressbooks/"

    def test_home_lists_addressbook(self, client, dav):
        root = _xml(_propfind(client, "/dav/addressbooks/", dav, depth="1"))

        hrefs = [h.text for h in root.findall("d:response/d:href", NS)]
        assert BOOK in hrefs
        book = next(r for r in root.findall("d:response", NS) if r.find("d:href", NS).text == BOOK)
        assert book.find(".//d:resourcetype/card:addressbook", NS) is not None
        assert book.find(".//d:current-user-privilege-set//d:write", NS) is not None

    def test_unknown_property_is_404_propstat(self, client, dav):
        body = '<d:propfind xmlns:d="DAV:"><d:prop><d:displayname/><d:quota-used-bytes/></d:prop></d:propfind>'

        root = _xml(_propfind(client, BOOK, dav, body=body))

        statuses = {ps.find("d:status", NS).text: ps for ps in root.findall(".//d:propstat", NS)}
        assert statuses["HTTP/1.1 200 OK"].find(".//d:displayname", NS).text == "PersonalCRM"
        assert statuses["HTTP/1.1 404 Not Found"].find(".//d:quota-used-bytes", NS) is not None


class TestListing:
    def test_contacts_listed_with_etags(self, client, dav, jwt):
        contact = _create(client, jwt)

        root = _xml(_propfind(client, BOOK, dav, depth="1"))

        items = [r for r in root.findall("d:response", NS) if r.find("d:href", NS).text != BOOK]
        assert [i.find("d:href", NS).text for i in items] == [f"{BOOK}{contact['id']}.vcf"]
        assert items[0].find(".//d:getetag", NS).text.startswith('"')

    def test_ctag_changes_when_contact_changes(self, client, dav, jwt):
        contact = _create(client, jwt)
        ctag = lambda: _xml(_propfind(client, BOOK, dav)).find(".//cs:getctag", NS).text  # noqa: E731
        before = ctag()

        client.patch(f"/api/contacts/{contact['id']}", json={"city": "Казань"}, headers=jwt)

        assert ctag() != before

    def test_multiget_returns_address_data(self, client, dav, jwt):
        contact = _create(client, jwt, company="Альфа")
        href = f"{BOOK}{contact['id']}.vcf"
        body = (
            '<card:addressbook-multiget xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
            f"<d:prop><d:getetag/><card:address-data/></d:prop><d:href>{href}</d:href>"
            f"<d:href>{BOOK}missing.vcf</d:href></card:addressbook-multiget>"
        )

        resp = client.request("REPORT", BOOK, headers={**dav, "Depth": "1"}, content=body)

        root = _xml(resp)
        found = {r.find("d:href", NS).text: r for r in root.findall("d:response", NS)}
        assert "ORG:Альфа" in found[href].find(".//card:address-data", NS).text
        assert found[f"{BOOK}missing.vcf"].find("d:status", NS).text == "HTTP/1.1 404 Not Found"


class TestReadWrite:
    def test_get_vcard(self, client, dav, jwt):
        contact = _create(client, jwt)

        resp = client.get(f"{BOOK}{contact['id']}.vcf", headers=dav)

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/vcard")
        assert resp.headers["etag"].startswith('"')
        assert "FN:Пётр Иванов" in resp.text

    def test_put_new_contact_keeps_client_href(self, client, dav, jwt):
        href = f"{BOOK}PHONE-UID-1.vcf"

        created = client.put(href, headers={**dav, "If-None-Match": "*"}, content=VCARD_FROM_PHONE.encode())
        fetched = client.get(href, headers=dav)

        assert created.status_code == 201
        assert created.headers["etag"]
        assert "UID:PHONE-UID-1" in fetched.text
        listed = client.get("/api/contacts/?q=Козлова", headers=jwt).json()
        assert listed[0]["phones"] == [{"value": "+7 921 555-12-12", "label": "мобильный"}]
        assert listed[0]["source"] == "phone"

    def test_put_update_keeps_crm_only_data(self, client, dav, jwt):
        contact = _create(client, jwt, priority="high", custom_fields=[{"key": "Telegram", "value": "@petr"}])
        href = f"{BOOK}{contact['id']}.vcf"
        etag = client.get(href, headers=dav).headers["etag"]
        card = client.get(href, headers=dav).text.replace("FN:Пётр Иванов", "FN:Пётр Иванов").replace(
            "END:VCARD", "TITLE:Директор\r\nEND:VCARD"
        )

        resp = client.put(href, headers={**dav, "If-Match": etag}, content=card.encode())

        assert resp.status_code == 204
        updated = client.get(f"/api/contacts/{contact['id']}", headers=jwt).json()
        assert updated["position"] == "Директор"
        assert updated["priority"] == "high"
        assert updated["custom_fields"] == [{"key": "Telegram", "value": "@petr"}]

    def test_stale_etag_is_412(self, client, dav, jwt):
        contact = _create(client, jwt)
        href = f"{BOOK}{contact['id']}.vcf"

        resp = client.put(href, headers={**dav, "If-Match": '"stale"'}, content=VCARD_FROM_PHONE.encode())

        assert resp.status_code == 412

    def test_create_over_existing_with_if_none_match_is_412(self, client, dav, jwt):
        contact = _create(client, jwt)

        resp = client.put(
            f"{BOOK}{contact['id']}.vcf", headers={**dav, "If-None-Match": "*"}, content=VCARD_FROM_PHONE.encode()
        )

        assert resp.status_code == 412

    def test_invalid_vcard_is_400(self, client, dav):
        resp = client.put(f"{BOOK}x.vcf", headers=dav, content=b"not a vcard")

        assert resp.status_code == 400

    def test_delete_moves_contact_to_trash(self, client, dav, jwt):
        contact = _create(client, jwt)
        client.post("/api/questions", json={"contact_id": contact["id"], "text": "?"}, headers=jwt)

        resp = client.delete(f"{BOOK}{contact['id']}.vcf", headers=dav)

        assert resp.status_code == 204
        assert client.get(f"/api/contacts/{contact['id']}", headers=jwt).status_code == 404
        assert client.get(f"{BOOK}{contact['id']}.vcf", headers=dav).status_code == 404
        assert client.get("/api/questions", headers=jwt).json() == []
        db = app.dependency_overrides[get_db]()
        trashed = client.portal.call(db["contacts_trash"].find_one, {"first_name": "Пётр"})
        assert trashed["deleted_via"] == "carddav"


class TestStatusForUi:
    def test_status_shows_how_to_connect_without_password(self, client, jwt, dav_password):
        resp = client.get("/api/carddav/status", headers=jwt)

        assert resp.status_code == 200
        assert resp.json() == {"enabled": True, "username": "admin", "path": "/dav/"}
        assert dav_password not in resp.text

    def test_status_when_no_password_issued(self, client, jwt):
        assert client.get("/api/carddav/status", headers=jwt).json()["enabled"] is False

    def test_status_requires_login(self, client):
        assert client.get("/api/carddav/status").status_code == 401
