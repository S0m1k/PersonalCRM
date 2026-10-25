"""
Вложения к контактам: загрузка, скачивание, удаление, лимиты и изоляция пользователей.

S3 — in-memory moto (conftest._fake_s3), MongoDB — mongomock.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.config import settings
from app.db import get_db
from app.main import app
from app.services.attachments import content_disposition, content_type_for, safe_file_name
from app.storage import get_storage

BOOK = "/dav/addressbooks/contacts/"


@pytest.fixture
def system_db():
    return AsyncMongoMockClient()["test_attachments"]


@pytest.fixture
def client(system_db):
    app.dependency_overrides[get_db] = lambda: system_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _register(client, email: str) -> dict:
    resp = client.post("/api/auth/register", json={"email": email, "password": "password-123"})
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _contact(client, auth, first_name: str = "Анна") -> str:
    resp = client.post("/api/contacts/", json={"first_name": first_name}, headers=auth)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _upload(client, auth, contact_id: str, name: str = "отчёт.pdf", data: bytes = b"%PDF-1.4 hello", ctype="application/pdf"):
    return client.post(
        f"/api/contacts/{contact_id}/attachments",
        files={"file": (name, data, ctype)},
        headers=auth,
    )


def _object_keys() -> list[str]:
    return [key for key, _ in get_storage().iter_keys()]


@pytest.fixture
def anna(client):
    auth = _register(client, "anna@example.com")
    return auth, _contact(client, auth)


class TestHappyPath:
    def test_upload_list_download_delete(self, client, anna):
        auth, cid = anna

        created = _upload(client, auth, cid)
        assert created.status_code == 201, created.text
        att = created.json()
        assert att["file_name"] == "отчёт.pdf"
        assert att["size"] == len(b"%PDF-1.4 hello")
        assert att["content_type"] == "application/pdf"
        assert "object_key" not in att

        listed = client.get(f"/api/contacts/{cid}/attachments", headers=auth).json()
        assert [a["id"] for a in listed] == [att["id"]]

        resp = client.get(f"/api/contacts/{cid}/attachments/{att['id']}", headers=auth)
        assert resp.status_code == 200
        assert resp.content == b"%PDF-1.4 hello"
        assert resp.headers["content-type"] == "application/octet-stream"
        assert resp.headers["x-content-type-options"] == "nosniff"
        assert resp.headers["content-disposition"].startswith("attachment;")
        assert quote("отчёт.pdf", safe="") in resp.headers["content-disposition"]

        assert client.delete(f"/api/contacts/{cid}/attachments/{att['id']}", headers=auth).status_code == 204
        assert client.get(f"/api/contacts/{cid}/attachments", headers=auth).json() == []
        assert _object_keys() == []

    def test_object_key_is_prefixed_with_user_id(self, client, anna):
        auth, cid = anna
        me = client.get("/api/auth/me", headers=auth).json()

        _upload(client, auth, cid)

        [key] = _object_keys()
        assert key.startswith(f"{me['id']}/{cid}/")
        assert "отчёт" not in key

    def test_large_file_roundtrip(self, client, anna):
        auth, cid = anna
        data = bytes(range(256)) * 40_000  # ~10 МБ — multipart upload и чтение кусками

        att = _upload(client, auth, cid, "big.bin", data, "application/octet-stream").json()

        resp = client.get(f"/api/contacts/{cid}/attachments/{att['id']}", headers=auth)
        assert resp.content == data

    def test_usage(self, client, anna):
        auth, cid = anna
        _upload(client, auth, cid, data=b"12345")

        usage = client.get("/api/attachments/usage", headers=auth).json()

        assert usage == {"used": 5, "quota": 500 * 1024 * 1024, "max_file_size": 25 * 1024 * 1024}

    def test_client_html_is_not_served_as_html(self, client, anna):
        auth, cid = anna
        att = _upload(client, auth, cid, "x.html", b"<script>alert(1)</script>", "text/html").json()

        resp = client.get(f"/api/contacts/{cid}/attachments/{att['id']}", headers=auth)

        assert resp.headers["content-type"] == "application/octet-stream"
        assert resp.headers["content-security-policy"] == "sandbox"


class TestLimits:
    def test_too_large_file_is_rejected(self, client, anna, monkeypatch):
        auth, cid = anna
        monkeypatch.setattr(settings, "attachment_max_mb", 1)

        resp = _upload(client, auth, cid, data=b"x" * (1024 * 1024 + 1))

        assert resp.status_code == 413
        assert _object_keys() == []

    def test_huge_body_is_rejected_before_parsing(self, client, anna, monkeypatch):
        auth, cid = anna
        monkeypatch.setattr(settings, "attachment_max_mb", 1)

        resp = _upload(client, auth, cid, data=b"x" * (2 * 1024 * 1024))

        assert resp.status_code == 413

    def test_quota(self, client, anna, monkeypatch):
        auth, cid = anna
        monkeypatch.setattr(settings, "attachments_quota_mb", 1)
        assert _upload(client, auth, cid, data=b"x" * 700_000).status_code == 201

        resp = _upload(client, auth, cid, data=b"x" * 700_000)

        assert resp.status_code == 413
        assert len(_object_keys()) == 1

    def test_empty_file_is_rejected(self, client, anna):
        auth, cid = anna
        assert _upload(client, auth, cid, data=b"").status_code == 422

    def test_unknown_contact(self, client, anna):
        auth, _ = anna
        assert _upload(client, auth, "64b000000000000000000000").status_code == 404
        assert client.get("/api/contacts/not-an-id/attachments", headers=auth).status_code == 404

    def test_requires_auth(self, client, anna):
        _, cid = anna
        assert client.get(f"/api/contacts/{cid}/attachments").status_code == 401

    def test_storage_not_configured(self, client, anna, monkeypatch):
        auth, cid = anna
        monkeypatch.setattr(settings, "s3_access_key", None)

        assert _upload(client, auth, cid).status_code == 503


class TestIsolation:
    def test_other_user_cannot_list_download_or_delete(self, client, anna):
        auth_a, cid = anna
        att = _upload(client, auth_a, cid).json()
        auth_b = _register(client, "boris@example.com")
        url = f"/api/contacts/{cid}/attachments"

        assert client.get(url, headers=auth_b).status_code == 404
        assert client.get(f"{url}/{att['id']}", headers=auth_b).status_code == 404
        assert client.delete(f"{url}/{att['id']}", headers=auth_b).status_code == 404
        assert _upload(client, auth_b, cid).status_code == 404

        assert client.get(f"{url}/{att['id']}", headers=auth_a).content == b"%PDF-1.4 hello"
        assert client.get("/api/attachments/usage", headers=auth_b).json()["used"] == 0

    def test_attachment_id_of_another_contact_is_404(self, client, anna):
        auth, cid = anna
        other = _contact(client, auth, "Борис")
        att = _upload(client, auth, cid).json()

        assert client.get(f"/api/contacts/{other}/attachments/{att['id']}", headers=auth).status_code == 404


class TestContactDeletion:
    def test_deleting_contact_deletes_its_files(self, client, anna):
        auth, cid = anna
        keep = _contact(client, auth, "Борис")
        _upload(client, auth, cid)
        _upload(client, auth, cid, "2.txt", b"two", "text/plain")
        kept = _upload(client, auth, keep).json()

        assert client.delete(f"/api/contacts/{cid}", headers=auth).status_code == 204

        assert len(_object_keys()) == 1
        assert [a["id"] for a in client.get(f"/api/contacts/{keep}/attachments", headers=auth).json()] == [kept["id"]]
        assert client.get("/api/attachments/usage", headers=auth).json()["used"] == kept["size"]

    def test_contact_deletion_survives_storage_failure(self, client, anna, monkeypatch):
        auth, cid = anna
        _upload(client, auth, cid)

        async def broken(*_args, **_kwargs):
            raise RuntimeError("S3 down")

        monkeypatch.setattr(type(get_storage()), "delete_many", broken)

        assert client.delete(f"/api/contacts/{cid}", headers=auth).status_code == 204


class TestHelpers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("../../etc/passwd", "passwd"),
            ("C:\\Users\\a\\doc.txt", "doc.txt"),
            ('a"b<c>.txt', "a_b_c_.txt"),
            ("line\nbreak.txt", "line_break.txt"),
            ("...", "file"),
            ("", "file"),
            (None, "file"),
        ],
    )
    def test_safe_file_name(self, raw, expected):
        assert safe_file_name(raw) == expected

    def test_long_name_keeps_extension(self):
        name = safe_file_name("я" * 500 + ".docx")
        assert len(name) == 200
        assert name.endswith(".docx")

    def test_content_disposition_is_header_safe(self):
        value = content_disposition('при"вет\\.pdf')
        assert value.startswith('attachment; filename=".pdf"; filename*=UTF-8\'\'')
        assert "\n" not in value and '"\\' not in value

    def test_content_type(self):
        assert content_type_for("a.png", "image/png") == "image/png"
        assert content_type_for("a.png", "not a type\r\nX: y") == "image/png"
        assert content_type_for("a.unknownext", None) == "application/octet-stream"


def test_carddav_delete_keeps_attachments_in_trash(client):
    """Удаление с телефона — в корзину: файлы остаются, чтобы контакт можно было вернуть."""
    import base64

    auth = _register(client, "anna@example.com")
    password = client.post("/api/auth/carddav-password", headers=auth).json()
    basic = {
        "Authorization": "Basic "
        + base64.b64encode(f"{password['username']}:{password['password']}".encode()).decode()
    }
    cid = _contact(client, auth)
    _upload(client, auth, cid)

    resp = client.request("DELETE", f"{BOOK}{cid}.vcf", headers=basic)

    assert resp.status_code == 204, resp.text
    assert len(_object_keys()) == 1


def test_backup_roundtrip(client, anna):
    """app.storage_backup: все объекты — в tar.gz и обратно, ключи и содержимое те же."""
    import io

    from app import storage_backup

    auth, cid = anna
    _upload(client, auth, cid, "a.txt", b"first", "text/plain")
    _upload(client, auth, cid, "b.bin", b"\x00\x01" * 1000, "application/octet-stream")
    storage = get_storage()
    before = {key: storage.open_sync(key).read() for key in _object_keys()}

    archive = io.BytesIO()
    assert storage_backup.dump(storage, archive) == 2
    storage._client.delete_objects(
        Bucket=storage.bucket, Delete={"Objects": [{"Key": k} for k in before]}
    )
    assert _object_keys() == []

    archive.seek(0)
    assert storage_backup.restore(storage, archive) == 2
    assert {key: storage.open_sync(key).read() for key in _object_keys()} == before
