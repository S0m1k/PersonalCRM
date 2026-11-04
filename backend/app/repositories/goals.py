"""
Репозиторий целей: единственный документ коллекции goals в базе пользователя + выборки данных для стратегии.

Документ: {_id: "goals", primary, enabled[], settings{подход: {...}}, assignments{contact_id: {circle}},
applied{contact_id: частота}, updated_at}. applied помнит, какие частоты поставила сама стратегия:
всё остальное считается заданным вручную.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.goals import default_settings
from ..services.strategy import ContactView, MetricsContext, contact_view
from . import contacts as contacts_repo
from . import events as events_repo
from . import interactions as interactions_repo

COLLECTION = "goals"
DOC_ID = "goals"
TOUCH_HISTORY_DAYS = 180

_PROJECTION = {
    "first_name": 1, "last_name": 1, "company": 1, "city": 1, "priority": 1, "tags": 1, "group_ids": 1,
    "life_areas": 1, "keep_in_touch": 1, "last_interaction_at": 1, "created_at": 1,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def empty_state() -> dict[str, Any]:
    return {"primary": None, "enabled": [], "settings": default_settings(), "assignments": {}, "applied": {}, "updated_at": None}


async def get_state(db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """Сохранённое состояние, дополненное настройками по умолчанию."""
    doc = await db[COLLECTION].find_one({"_id": DOC_ID}) or {}
    base = empty_state()
    return {
        "primary": doc.get("primary"),
        "enabled": list(doc.get("enabled") or []),
        "settings": {**base["settings"], **(doc.get("settings") or {})},
        "assignments": dict(doc.get("assignments") or {}),
        "applied": dict(doc.get("applied") or {}),
        "updated_at": doc.get("updated_at"),
    }


async def save_state(db: AsyncIOMotorDatabase, changes: dict[str, Any]) -> dict[str, Any]:
    await db[COLLECTION].update_one(
        {"_id": DOC_ID}, {"$set": {**changes, "updated_at": _utcnow()}}, upsert=True
    )
    return await get_state(db)


async def existing_contact_ids(db: AsyncIOMotorDatabase, ids: list[str]) -> set[str]:
    oids = []
    for cid in ids:
        try:
            oids.append(ObjectId(cid))
        except (InvalidId, TypeError):
            continue
    docs = await db[contacts_repo.COLLECTION].find({"_id": {"$in": oids}}, {"_id": 1}).to_list(length=None)
    return {str(d["_id"]) for d in docs}


async def load_contacts(db: AsyncIOMotorDatabase, now: Optional[datetime] = None) -> list[ContactView]:
    docs = await db[contacts_repo.COLLECTION].find({}, _PROJECTION).to_list(length=None)
    last = await interactions_repo.latest_map(db, [str(d["_id"]) for d in docs], now)
    return [contact_view(d, last.get(str(d["_id"]))) for d in docs]


async def load_touches(db: AsyncIOMotorDatabase, now: datetime, days: int = TOUCH_HISTORY_DAYS) -> list[tuple[list[str], datetime]]:
    """Взаимодействия и прошедшие события с людьми за последние days дней."""
    since = now - timedelta(days=days)
    touches: list[tuple[list[str], datetime]] = []
    async for doc in db[interactions_repo.COLLECTION].find(
        {"occurred_at": {"$gte": since, "$lte": now}}, {"contact_ids": 1, "occurred_at": 1}
    ):
        touches.append(([str(c) for c in doc.get("contact_ids") or []], _aware(doc["occurred_at"])))
    async for doc in db[events_repo.COLLECTION].find(
        {"start": {"$gte": since, "$lte": now}, "contact_ids.0": {"$exists": True}}, {"contact_ids": 1, "start": 1}
    ):
        touches.append(([str(c) for c in doc.get("contact_ids") or []], _aware(doc["start"])))
    return touches


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def metrics_context(db: AsyncIOMotorDatabase, state: dict, period: int, now: Optional[datetime] = None) -> MetricsContext:
    now = now or _utcnow()
    return MetricsContext(
        contacts=await load_contacts(db, now),
        touches=await load_touches(db, now),
        assignments=state["assignments"],
        now=now,
        period=period,
    )


async def apply_frequencies(db: AsyncIOMotorDatabase, frequencies: dict[str, int]) -> int:
    """Записать частоты контактам; updated_at не трогаем (наружу это не синхронизируется)."""
    changed = 0
    for cid, days in frequencies.items():
        result = await db[contacts_repo.COLLECTION].update_one(
            {"_id": ObjectId(cid)}, {"$set": {"keep_in_touch.frequency_days": days}}
        )
        changed += result.matched_count
    return changed
