"""
Рейт-лимиты: правила по путям, ответ 429, ключ по пользователю / IP, fail-open без Redis.

Счётчики — в памяти (REDIS_URL пуст), перед каждым тестом сбрасываются.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app import ratelimit
from app.config import settings
from app.db import get_db
from app.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    ratelimit.reset_limiter()
    db = AsyncMongoMockClient()["test_ratelimit"]
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    ratelimit.reset_limiter()


def _login(client, password: str = "wrong", headers: dict | None = None):
    return client.post(
        "/api/auth/login/json", json={"username": "admin", "password": password}, headers=headers or {}
    )


@pytest.mark.parametrize(
    ("method", "path", "rule"),
    [
        ("POST", "/api/auth/register", "register"),
        ("POST", "/api/auth/login", "login"),
        ("POST", "/api/auth/login/json", "login"),
        ("PROPFIND", "/dav/addressbooks/contacts/", "dav"),
        ("PROPFIND", "/.well-known/carddav", "dav"),
        ("POST", "/api/webhooks/microsoft", "webhook"),
        ("POST", "/api/auth/password", "credentials"),
        ("POST", "/api/import/upload", "import"),
        ("POST", "/api/sync/contacts/abc", "sync"),
        ("POST", "/api/contacts/abc/attachments", "upload"),
        ("DELETE", "/api/contacts/abc/attachments/def", "write"),
        ("GET", "/api/contacts/abc/attachments/def", "read"),
        ("POST", "/api/assistant/capture", "ai"),
        ("POST", "/api/assistant/ask", "ai"),
        ("POST", "/api/assistant/jobs/abc/apply", "write"),
        ("GET", "/api/assistant/jobs/abc", "read"),
        ("PATCH", "/api/contacts/abc", "write"),
        ("DELETE", "/api/questions/abc", "write"),
        ("GET", "/api/contacts/", "read"),
    ],
)
def test_rule_selection(method, path, rule):
    assert ratelimit.find_rule(method, path).name == rule


def test_health_is_not_limited():
    assert ratelimit.find_rule("GET", "/api/health") is None


def test_login_is_limited_per_ip(client):
    statuses = [_login(client).status_code for _ in range(11)]

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


def test_429_has_retry_after_and_cors(client):
    for _ in range(10):
        _login(client)

    resp = _login(client, headers={"Origin": settings.frontend_url})

    assert resp.status_code == 429
    assert int(resp.headers["retry-after"]) >= 1
    assert resp.headers["access-control-allow-origin"] == settings.frontend_url


def test_limit_does_not_block_other_rules(client):
    for _ in range(11):
        _login(client)

    assert client.get("/api/health").status_code == 200
    assert client.post(
        "/api/auth/register", json={"email": "a@b.co", "password": "password-123"}
    ).status_code == 201


def test_users_have_separate_buckets(client, monkeypatch):
    rule = ratelimit.Rule(name="read", limits=tuple(ratelimit.parse_many("2/minute")), key="user",
                          matches=lambda m, p: m == "GET" and p == "/api/auth/me")
    monkeypatch.setattr(ratelimit, "RULES", (rule,))
    tokens = []
    for email in ("a@b.co", "c@d.co"):
        resp = client.post("/api/auth/register", json={"email": email, "password": "password-123"})
        tokens.append({"Authorization": f"Bearer {resp.json()['access_token']}"})

    first = [client.get("/api/auth/me", headers=tokens[0]).status_code for _ in range(3)]
    second = client.get("/api/auth/me", headers=tokens[1]).status_code

    assert first == [200, 200, 429]
    assert second == 200


def test_x_real_ip_is_ignored_unless_trusted(client):
    for i in range(10):
        _login(client, headers={"X-Real-IP": f"10.0.0.{i}"})

    assert _login(client, headers={"X-Real-IP": "10.0.0.99"}).status_code == 429


def test_x_real_ip_is_used_behind_proxy(client, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    for _ in range(10):
        _login(client, headers={"X-Real-IP": "10.0.0.1"})

    assert _login(client, headers={"X-Real-IP": "10.0.0.1"}).status_code == 429
    assert _login(client, headers={"X-Real-IP": "10.0.0.2"}).status_code == 401


def test_register_is_limited_per_ip(client):
    statuses = [
        client.post("/api/auth/register", json={"email": f"u{i}@b.co", "password": "password-123"}).status_code
        for i in range(6)
    ]

    assert statuses == [201] * 5 + [429]


def test_login_is_limited_per_account_across_ips(client, monkeypatch):
    monkeypatch.setattr(settings, "trust_proxy_headers", True)
    # 20 попыток с 20 разных адресов (лимит по IP не срабатывает), 21-я — уже 429
    statuses = [_login(client, headers={"X-Real-IP": f"10.1.0.{i}"}).status_code for i in range(21)]

    assert statuses[:20] == [401] * 20
    assert statuses[20] == 429


@pytest.mark.parametrize(
    ("raw", "bucket"),
    [
        ("203.0.113.7", "203.0.113.7"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff::9", "2001:db8:1:2::/64"),
        ("not-an-ip", "not-an-ip"),
    ],
)
def test_ipv6_clients_share_a_64_bucket(raw, bucket):
    assert ratelimit._ip_bucket(raw) == bucket


def test_redis_url_gets_async_prefix(monkeypatch):
    seen = {}

    class FakeStorage:
        def __init__(self, uri, **options):
            seen["uri"], seen["options"] = uri, options

    monkeypatch.setattr(ratelimit, "RedisStorage", FakeStorage)
    monkeypatch.setattr(ratelimit, "RateLimiter", lambda storage: storage)
    monkeypatch.setattr(settings, "redis_url", "redis://redis:6379/0")

    ratelimit.build_limiter()

    assert seen["uri"] == "async+redis://redis:6379/0"
    assert seen["options"]["implementation"] == "redispy"


def test_disabled_limits(client, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    assert all(_login(client).status_code == 401 for _ in range(15))


async def test_storage_failure_lets_requests_through(monkeypatch):
    # Порт 1 закрыт: соединение с Redis сразу отклоняется
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:1/0")
    limiter = ratelimit.build_limiter()
    rule = ratelimit.find_rule("POST", "/api/auth/login")

    started = time.monotonic()
    results = [await limiter.check(rule, "ip:1.2.3.4") for _ in range(15)]

    assert results == [None] * 15
    # После первого сбоя хранилище не дёргается — запросы не ждут таймаута
    assert time.monotonic() - started < 2
