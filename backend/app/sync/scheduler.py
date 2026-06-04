"""
Фоновый планировщик (APScheduler) для Sprint 3.

Задачи:
  - periodic_sync           каждые 30 мин: delta/incremental sync всех подключений
                            (fallback, если вебхуки не сработали)
  - refresh_expiring_tokens каждые 15 мин: проактивно обновляет токены,
                            истекающие в ближайшие 10 минут
  - renew_webhooks          каждые 12 часов: продлевает Microsoft-подписки

ВАЖНО: рассчитан на один процесс (single-user, uvicorn без --workers >1).
При нескольких воркерах задачи будут дублироваться — нужен внешний lock.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..db import get_db
from ..models.sync import SyncError, SyncStats
from ..repositories import sync as sync_repo
from .oauth import google_refresh_token, ms_refresh_token
from .microsoft import renew_contact_subscription

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


# ---------------------------------------------------------------------------
# Задачи
# ---------------------------------------------------------------------------


async def periodic_sync() -> None:
    """Периодическая синхронизация всех подключений с включёнными контактами."""
    # Импорт здесь — избегаем циклического импорта с routers.sync
    from ..routers.sync import _run_google_sync, _run_microsoft_sync

    db = get_db()
    connections = await sync_repo.list_connections(db)
    for conn in connections:
        if not conn.sync_contacts:
            continue
        stats, errors = SyncStats(), []
        started = datetime.now(timezone.utc)
        log = await sync_repo.create_log(
            db, connection_id=conn.id, type="contacts", action="scheduled", started_at=started
        )
        try:
            access_token, _ = sync_repo.get_decrypted_tokens(conn)
            if conn.provider == "microsoft":
                await _run_microsoft_sync(db, conn, access_token, stats, errors)
            elif conn.provider == "google":
                await _run_google_sync(db, conn, access_token, stats, errors)
        except Exception as exc:  # noqa: BLE001
            logger.error("periodic_sync failed for %s: %s", conn.id, exc)
            stats.errors += 1
            errors.append(SyncError(error=str(exc)))
        await sync_repo.update_log(
            db, log.id, stats=stats, errors=errors, completed_at=datetime.now(timezone.utc)
        )


async def refresh_expiring_tokens() -> None:
    """Обновить токены, истекающие в ближайшие 10 минут."""
    db = get_db()
    threshold = datetime.now(timezone.utc) + timedelta(minutes=10)
    for conn in await sync_repo.list_connections(db):
        if not conn.token_expires_at:
            continue
        exp = conn.token_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp > threshold:
            continue
        _, refresh_token = sync_repo.get_decrypted_tokens(conn)
        if not refresh_token:
            continue
        try:
            if conn.provider == "microsoft":
                data = await ms_refresh_token(refresh_token)
            elif conn.provider == "google":
                data = await google_refresh_token(refresh_token)
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("token refresh failed for %s: %s", conn.id, exc)
            continue

        new_expiry = datetime.now(timezone.utc) + timedelta(seconds=int(data.get("expires_in", 3600)))
        fields = {
            "access_token": data.get("access_token", ""),
            "token_expires_at": new_expiry,
        }
        # Google при refresh не возвращает новый refresh_token — сохраняем старый
        if data.get("refresh_token"):
            fields["refresh_token"] = data["refresh_token"]
        await sync_repo.update_connection(db, conn.id, **fields)
        logger.info("refreshed token for connection %s", conn.id)


async def renew_webhooks() -> None:
    """Продлить Microsoft-подписки, истекающие в ближайшие сутки."""
    db = get_db()
    soon = datetime.now(timezone.utc) + timedelta(days=1)
    for conn in await sync_repo.list_connections(db):
        if conn.provider != "microsoft" or not conn.webhook_subscription_id:
            continue
        exp = conn.webhook_expires_at
        if exp and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp and exp > soon:
            continue
        try:
            access_token, _ = sync_repo.get_decrypted_tokens(conn)
            await renew_contact_subscription(access_token, conn.webhook_subscription_id)
            await sync_repo.update_connection(
                db, conn.id, webhook_expires_at=datetime.now(timezone.utc) + timedelta(days=2, hours=12)
            )
            logger.info("renewed webhook subscription for %s", conn.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("renew webhook failed for %s: %s", conn.id, exc)


# ---------------------------------------------------------------------------
# Управление жизненным циклом
# ---------------------------------------------------------------------------


def start_scheduler() -> None:
    """Зарегистрировать задачи и запустить планировщик."""
    if scheduler.running:
        return
    scheduler.add_job(periodic_sync, "interval", minutes=30, id="periodic_sync", replace_existing=True)
    scheduler.add_job(refresh_expiring_tokens, "interval", minutes=15, id="refresh_tokens", replace_existing=True)
    scheduler.add_job(renew_webhooks, "interval", hours=12, id="renew_webhooks", replace_existing=True)
    scheduler.start()
    logger.info("Фоновый планировщик запущен (periodic_sync/refresh_tokens/renew_webhooks)")


def shutdown_scheduler() -> None:
    """Остановить планировщик."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Фоновый планировщик остановлен")
