"""
Синхронизация календарей (Sprint 7): провайдер ↔ коллекция events в базе пользователя.

- run_calendar_sync — подтянуть изменения (Graph delta / Google syncToken) и обновить события,
  привязав их к людям по email/телефону участников. Протухшее состояние → полная синхронизация.
- push_event / delete_remote — записать событие CRM у провайдера (двусторонний sync).
  Открытые вопросы «на встрече» дописываются в описание, только если у события push_questions.
- Конфликты: последний записавший побеждает (как у контактов).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from types import ModuleType
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.event import Attendee, as_utc
from ..models.sync import SyncConnection, SyncError, SyncStats
from ..repositories import events as events_repo
from ..repositories import sync as sync_repo
from . import calendar_google, calendar_microsoft
from .calendar_common import CalendarAccessError, SyncStateExpired, with_questions_block

logger = logging.getLogger(__name__)

_ENGINES: dict[str, ModuleType] = {"microsoft": calendar_microsoft, "google": calendar_google}


def engine_for(provider: str) -> ModuleType:
    engine = _ENGINES.get(provider)
    if engine is None:
        raise ValueError(f"Календарь провайдера {provider!r} не поддерживается")
    return engine


async def _mark_needs_consent(db: AsyncIOMotorDatabase, conn: SyncConnection) -> None:
    await sync_repo.update_connection(db, conn.id, calendar_needs_consent=True)


async def _apply_upsert(
    db: AsyncIOMotorDatabase, conn: SyncConnection, external_id: str, data: dict, stats: SyncStats
) -> None:
    if data.get("start") is None:
        stats.skipped += 1
        return
    auto = await events_repo.match_contacts(db, [Attendee(**a) for a in data.get("attendees", [])])
    existing = await events_repo.find_external(db, conn.id, external_id)
    if existing is None:
        await events_repo.insert_event(
            db,
            {
                **data,
                "contact_ids": auto,
                "source": conn.provider,
                "connection_id": conn.id,
                "external_id": external_id,
            },
        )
        stats.created += 1
        return
    links = events_repo.combine_links(
        auto, existing.get("manual_contact_ids") or [], existing.get("excluded_contact_ids") or []
    )
    await events_repo.update_event_doc(db, str(existing["_id"]), {**data, "contact_ids": links})
    stats.updated += 1


async def run_calendar_sync(
    db: AsyncIOMotorDatabase, conn: SyncConnection, stats: SyncStats, errors: list[SyncError]
) -> None:
    """Подтянуть изменения календаря подключения (мутирует stats и errors)."""
    engine = engine_for(conn.provider)
    access_token, _ = sync_repo.get_decrypted_tokens(conn)
    try:
        try:
            changes, next_state = await engine.list_changes(access_token, conn.calendar_sync_state)
        except SyncStateExpired:
            logger.info("calendar sync state expired for %s, full resync", conn.id)
            changes, next_state = await engine.list_changes(access_token, None)
    except CalendarAccessError:
        await _mark_needs_consent(db, conn)
        raise

    for change in changes:
        external_id = change["external_id"]
        try:
            if change["action"] == "deleted":
                if await events_repo.delete_external(db, conn.id, external_id):
                    stats.deleted += 1
            else:
                await _apply_upsert(db, conn, external_id, change["data"], stats)
        except Exception as exc:  # noqa: BLE001 — одно кривое событие не ломает остальные
            logger.warning("calendar event %s failed: %s", external_id, exc)
            stats.errors += 1
            errors.append(SyncError(contact_name=change.get("data", {}).get("title", ""), error=str(exc)))

    await sync_repo.update_connection(
        db,
        conn.id,
        calendar_sync_state=next_state or conn.calendar_sync_state,
        calendar_last_sync=datetime.now(timezone.utc),
        calendar_needs_consent=False,
    )


async def _description_for_push(db: AsyncIOMotorDatabase, doc: dict) -> str:
    description = doc.get("description", "")
    if not doc.get("push_questions"):
        return with_questions_block(description, [])
    out = await events_repo.to_out(db, doc)
    return with_questions_block(description, [(q.contact_name, q.text) for q in out.questions])


async def push_event(db: AsyncIOMotorDatabase, conn: SyncConnection, doc: dict) -> dict:
    """
    Создать или обновить событие у провайдера. Возвращает поля, которые нужно сохранить
    в документе (external_id, etag …) — сам документ не меняет: вызывающий сохраняет правку
    только после успешной записи у провайдера.
    CalendarAccessError — нет прав на календарь (подключение помечается для переподключения).
    """
    engine = engine_for(conn.provider)
    access_token, _ = sync_repo.get_decrypted_tokens(conn)
    doc = {**doc, "start": as_utc(doc["start"]), "end": as_utc(doc["end"])}
    description = await _description_for_push(db, doc)
    try:
        if doc.get("external_id") and doc.get("connection_id") == conn.id:
            remote = await engine.update_event(access_token, doc["external_id"], doc, description)
            external_id = doc["external_id"]
        else:
            external_id, remote = await engine.create_event(access_token, doc, description)
    except CalendarAccessError:
        await _mark_needs_consent(db, conn)
        raise
    return {
        "source": conn.provider,
        "connection_id": conn.id,
        "external_id": external_id,
        "etag": remote.get("etag"),
        "web_link": remote.get("web_link") or doc.get("web_link", ""),
    }


async def delete_remote(db: AsyncIOMotorDatabase, conn: SyncConnection, doc: dict) -> None:
    engine = engine_for(conn.provider)
    access_token, _ = sync_repo.get_decrypted_tokens(conn)
    try:
        await engine.delete_event(access_token, doc["external_id"])
    except CalendarAccessError:
        await _mark_needs_consent(db, conn)
        raise


async def connection_for(db: AsyncIOMotorDatabase, doc: dict) -> Optional[SyncConnection]:
    """Подключение, из которого пришло событие (None — событие только в CRM)."""
    if not doc.get("connection_id") or not doc.get("external_id"):
        return None
    return await sync_repo.get_connection(db, doc["connection_id"])
