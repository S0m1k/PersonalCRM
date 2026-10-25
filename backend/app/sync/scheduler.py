"""
Фоновый планировщик (APScheduler) для Sprint 3.

Задачи:
  - periodic_sync           каждые SYNC_INTERVAL_MINUTES (по умолч. 30): delta sync всех подключений
                            (fallback, если вебхуки не сработали); календари — тоже (Sprint 7)
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
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..config import settings
from ..auth import ensure_legacy_admin, tenant_db
from ..db import get_db
from ..repositories import users as users_repo
from ..models.sync import SyncError, SyncStats
from ..repositories import sync as sync_repo
from .oauth import google_refresh_token, ms_refresh_token
from .calendar import run_calendar_sync
from .calendar_common import CalendarAccessError
from .microsoft import renew_contact_subscription
from .oauth import calendar_scope_granted

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


# ---------------------------------------------------------------------------
# Задачи
# ---------------------------------------------------------------------------


async def user_dbs() -> list[AsyncIOMotorDatabase]:
    """Базы всех пользователей: фоновые задачи обходят каждую."""
    system_db = get_db()
    await ensure_legacy_admin(system_db)
    return [tenant_db(system_db, u.db_name) for u in await users_repo.list_users(system_db)]


async def _for_each_user(job, name: str) -> None:
    """Запустить job(db) для каждой базы; сбой у одного пользователя не мешает остальным."""
    for db in await user_dbs():
        try:
            await job(db)
        except Exception as exc:  # noqa: BLE001
            logger.error("%s failed for %s: %s", name, db.name, exc)


async def periodic_sync() -> None:
    """Периодическая синхронизация всех подключений с включёнными контактами."""
    await _for_each_user(_periodic_sync_db, "periodic_sync")


async def refresh_expiring_tokens() -> None:
    """Обновить токены, истекающие в ближайшие 10 минут."""
    await _for_each_user(_refresh_tokens_db, "refresh_expiring_tokens")


async def renew_webhooks() -> None:
    """Продлить Microsoft-подписки, истекающие в ближайшие сутки."""
    await _for_each_user(_renew_webhooks_db, "renew_webhooks")


async def _periodic_sync_db(db: AsyncIOMotorDatabase) -> None:
    # Импорт здесь — избегаем циклического импорта с routers.sync
    from ..routers.sync import _run_google_sync, _run_microsoft_sync

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
    for conn in connections:
        await _calendar_sync_conn(db, conn)


async def _calendar_sync_conn(db: AsyncIOMotorDatabase, conn) -> None:
    """Календарь подключения — если включён и права выданы (иначе ждём переподключения)."""
    if not conn.sync_calendar or conn.calendar_needs_consent:
        return
    if not calendar_scope_granted(conn.provider, conn.scopes):
        return
    stats, errors = SyncStats(), []
    log = await sync_repo.create_log(db, connection_id=conn.id, type="calendar", action="scheduled")
    try:
        await run_calendar_sync(db, conn, stats, errors)
    except CalendarAccessError:
        errors.append(SyncError(error="Нет доступа к календарю — нужно переподключение"))
    except Exception as exc:  # noqa: BLE001
        logger.error("calendar sync failed for %s: %s", conn.id, exc)
        stats.errors += 1
        errors.append(SyncError(error=str(exc)))
    await sync_repo.update_log(db, log.id, stats=stats, errors=errors, completed_at=datetime.now(timezone.utc))


async def _refresh_tokens_db(db: AsyncIOMotorDatabase) -> None:
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
                data = await ms_refresh_token(refresh_token, conn.scopes)
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
        if data.get("scope"):
            fields["scopes"] = data["scope"]
        await sync_repo.update_connection(db, conn.id, **fields)
        logger.info("refreshed token for connection %s", conn.id)


async def _renew_webhooks_db(db: AsyncIOMotorDatabase) -> None:
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


def register_jobs(target: AsyncIOScheduler) -> None:
    """Добавить фоновые задачи в планировщик (без запуска)."""
    target.add_job(
        periodic_sync,
        "interval",
        minutes=settings.sync_interval_minutes,
        id="periodic_sync",
        replace_existing=True,
    )
    target.add_job(refresh_expiring_tokens, "interval", minutes=15, id="refresh_tokens", replace_existing=True)
    target.add_job(renew_webhooks, "interval", hours=12, id="renew_webhooks", replace_existing=True)


def start_scheduler() -> None:
    """Зарегистрировать задачи и запустить планировщик."""
    if scheduler.running:
        return
    register_jobs(scheduler)
    scheduler.start()
    logger.info("Фоновый планировщик запущен (periodic_sync/refresh_tokens/renew_webhooks)")


def shutdown_scheduler() -> None:
    """Остановить планировщик."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Фоновый планировщик остановлен")
