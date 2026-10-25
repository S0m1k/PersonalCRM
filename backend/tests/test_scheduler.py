"""
Тесты фонового планировщика: регистрация задач и логика refresh токенов.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from mongomock_motor import AsyncMongoMockClient

from app.repositories import sync as sync_repo
from app.sync import scheduler as sch


async def test_jobs_registered():
    """start_scheduler регистрирует три задачи."""
    sch.start_scheduler()
    try:
        ids = {j.id for j in sch.scheduler.get_jobs()}
        assert {"periodic_sync", "refresh_tokens", "renew_webhooks"} <= ids
    finally:
        sch.shutdown_scheduler()


def test_periodic_sync_interval_from_settings(monkeypatch):
    """Интервал periodic_sync берётся из SYNC_INTERVAL_MINUTES."""
    monkeypatch.setattr(sch.settings, "sync_interval_minutes", 5)
    fresh = AsyncIOScheduler(timezone="UTC")

    sch.register_jobs(fresh)

    assert fresh.get_job("periodic_sync").trigger.interval == timedelta(minutes=5)


async def test_refresh_expiring_token(monkeypatch):
    """Токен, истекающий скоро, обновляется через refresh."""
    db = AsyncMongoMockClient()["sched_test1"]
    monkeypatch.setattr(sch, "get_db", lambda: db)

    async def fake_ms_refresh(rt: str, scopes=None) -> dict:
        assert rt == "the-refresh-token"
        return {"access_token": "fresh-access", "expires_in": 3600}

    monkeypatch.setattr(sch, "ms_refresh_token", fake_ms_refresh)

    conn = await sync_repo.create_connection(
        db,
        provider="microsoft",
        access_token="stale-access",
        refresh_token="the-refresh-token",
        token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # уже истёк
    )

    await sch.refresh_expiring_tokens()

    updated = await sync_repo.get_connection(db, conn.id)
    access, _ = sync_repo.get_decrypted_tokens(updated)
    assert access == "fresh-access"


async def test_refresh_skips_fresh_token(monkeypatch):
    """Токен с большим запасом не трогаем."""
    db = AsyncMongoMockClient()["sched_test2"]
    monkeypatch.setattr(sch, "get_db", lambda: db)

    called = {"n": 0}

    async def fake_ms_refresh(rt: str, scopes=None) -> dict:
        called["n"] += 1
        return {"access_token": "x", "expires_in": 3600}

    monkeypatch.setattr(sch, "ms_refresh_token", fake_ms_refresh)

    await sync_repo.create_connection(
        db,
        provider="microsoft",
        access_token="good",
        refresh_token="rt",
        token_expires_at=datetime.now(timezone.utc) + timedelta(hours=5),  # ещё свежий
    )

    await sch.refresh_expiring_tokens()
    assert called["n"] == 0
