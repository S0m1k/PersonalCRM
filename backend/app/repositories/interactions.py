"""
Репозиторий взаимодействий (Timeline, коллекция interactions в базе пользователя).

last_interaction_at контакта = максимум из его взаимодействий и прошедших событий календаря;
пересчитывается при каждом создании / изменении / удалении взаимодействия.
"""

from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
from typing import Iterable, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.interaction import (
    InteractionCreate,
    InteractionOut,
    InteractionPage,
    InteractionUpdate,
    to_aware_utc,
)
from . import contacts as contacts_repo
from . import events as events_repo

COLLECTION = "interactions"
DEFAULT_LIMIT = 30
MAX_LIMIT = 200


class InvalidCursor(ValueError):
    """Курсор пагинации испорчен."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[COLLECTION].create_index([("contact_ids", 1), ("occurred_at", -1)])
    await db[COLLECTION].create_index([("occurred_at", -1)])


# ---------------------------------------------------------------------------
# last_interaction_at
# ---------------------------------------------------------------------------


async def latest_for_contact(db: AsyncIOMotorDatabase, contact_id: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Самое позднее прошедшее взаимодействие или событие календаря с этим человеком."""
    now = now or _utcnow()
    found: list[datetime] = []
    doc = await db[COLLECTION].find_one(
        {"contact_ids": contact_id, "occurred_at": {"$lte": now}}, sort=[("occurred_at", -1)]
    )
    if doc:
        found.append(to_aware_utc(doc["occurred_at"]))
    event = await db[events_repo.COLLECTION].find_one(
        {"contact_ids": contact_id, "start": {"$lte": now}}, sort=[("start", -1)]
    )
    if event:
        found.append(to_aware_utc(event["start"]))
    return max(found) if found else None


async def latest_map(
    db: AsyncIOMotorDatabase, contact_ids: Iterable[str], now: Optional[datetime] = None
) -> dict[str, datetime]:
    """{contact_id: последнее взаимодействие} одним проходом; людей без взаимодействий в словаре нет."""
    now = now or _utcnow()
    wanted = set(contact_ids)
    if not wanted:
        return {}
    result: dict[str, datetime] = {}

    def take(cid: str, when: datetime) -> None:
        when = to_aware_utc(when)
        if cid in wanted and (cid not in result or when > result[cid]):
            result[cid] = when

    query = {"contact_ids": {"$in": list(wanted)}}
    async for doc in db[COLLECTION].find({**query, "occurred_at": {"$lte": now}}, {"contact_ids": 1, "occurred_at": 1}):
        for cid in doc.get("contact_ids") or []:
            take(cid, doc["occurred_at"])
    async for doc in db[events_repo.COLLECTION].find({**query, "start": {"$lte": now}}, {"contact_ids": 1, "start": 1}):
        for cid in doc.get("contact_ids") or []:
            take(cid, doc["start"])
    return result


async def recompute_last_interaction(db: AsyncIOMotorDatabase, contact_ids: Iterable[str]) -> None:
    """Пересчитать и записать last_interaction_at этим контактам."""
    for cid in dict.fromkeys(contact_ids):
        await contacts_repo.set_last_interaction(db, cid, await latest_for_contact(db, cid))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_interaction(db: AsyncIOMotorDatabase, data: InteractionCreate) -> InteractionOut:
    await ensure_indexes(db)
    now = _utcnow()
    doc = data.model_dump()
    doc["occurred_at"] = data.occurred_at or now
    doc["created_at"] = now
    doc["updated_at"] = now
    result = await db[COLLECTION].insert_one(doc)
    await recompute_last_interaction(db, data.contact_ids)
    return InteractionOut.from_mongo({**doc, "_id": result.inserted_id})


async def get_interaction(db: AsyncIOMotorDatabase, interaction_id: str) -> Optional[InteractionOut]:
    oid = _parse_oid(interaction_id)
    doc = await db[COLLECTION].find_one({"_id": oid}) if oid else None
    return InteractionOut.from_mongo(doc) if doc else None


async def update_interaction(
    db: AsyncIOMotorDatabase, interaction_id: str, data: InteractionUpdate
) -> Optional[InteractionOut]:
    oid = _parse_oid(interaction_id)
    if oid is None:
        return None
    before = await db[COLLECTION].find_one({"_id": oid})
    if before is None:
        return None
    changes = data.model_dump(exclude_none=True)
    changes["updated_at"] = _utcnow()
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    await recompute_last_interaction(db, [*(before.get("contact_ids") or []), *(doc.get("contact_ids") or [])])
    return InteractionOut.from_mongo(doc)


async def delete_interaction(db: AsyncIOMotorDatabase, interaction_id: str) -> bool:
    oid = _parse_oid(interaction_id)
    if oid is None:
        return False
    doc = await db[COLLECTION].find_one_and_delete({"_id": oid})
    if doc is None:
        return False
    await recompute_last_interaction(db, doc.get("contact_ids") or [])
    return True


async def unlink_contact(db: AsyncIOMotorDatabase, contact_id: str) -> None:
    """Контакт удалён: убрать его из взаимодействий; опустевшие (без людей) удалить."""
    await db[COLLECTION].update_many({"contact_ids": contact_id}, {"$pull": {"contact_ids": contact_id}})
    await db[COLLECTION].delete_many({"contact_ids": {"$size": 0}})


# ---------------------------------------------------------------------------
# Лента
# ---------------------------------------------------------------------------


def encode_cursor(when: datetime, item_id: str) -> str:
    return base64.urlsafe_b64encode(f"{to_aware_utc(when).isoformat()}|{item_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, ObjectId]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        stamp, _, item_id = raw.partition("|")
        return to_aware_utc(datetime.fromisoformat(stamp)), ObjectId(item_id)
    except (ValueError, InvalidId, UnicodeError):
        raise InvalidCursor("Некорректный курсор") from None


def _time_filters(field: str, from_: Optional[datetime], to: Optional[datetime], cursor: Optional[tuple]) -> list[dict]:
    """Условия по времени: границы from/to и «строго после курсора» при сортировке (время, id) по убыванию."""
    clauses: list[dict] = []
    if from_ is not None:
        clauses.append({field: {"$gte": to_aware_utc(from_)}})
    if to is not None:
        clauses.append({field: {"$lte": to_aware_utc(to)}})
    if cursor is not None:
        when, oid = cursor
        clauses.append({"$or": [{field: {"$lt": when}}, {field: when, "_id": {"$lt": oid}}]})
    return clauses


def _regex(q: str) -> dict:
    return {"$regex": re.escape(q.strip()), "$options": "i"}


async def list_page(
    db: AsyncIOMotorDatabase,
    contact_id: Optional[str] = None,
    kind: Optional[str] = None,
    from_: Optional[datetime] = None,
    to: Optional[datetime] = None,
    q: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
    include_events: bool = False,
) -> InteractionPage:
    """Лента, новые сверху. Прошедшие события календаря с людьми подмешиваются как «встречи»."""
    limit = max(1, min(limit, MAX_LIMIT))
    parsed = decode_cursor(cursor) if cursor else None

    clauses = _time_filters("occurred_at", from_, to, parsed)
    if contact_id:
        clauses.append({"contact_ids": contact_id})
    if kind:
        clauses.append({"kind": kind})
    if q and q.strip():
        clauses.append({"$or": [{"title": _regex(q)}, {"body": _regex(q)}]})
    docs = (
        await db[COLLECTION]
        .find({"$and": clauses} if clauses else {})
        .sort([("occurred_at", -1), ("_id", -1)])
        .limit(limit + 1)
        .to_list(length=limit + 1)
    )
    items = [(to_aware_utc(d["occurred_at"]), str(d["_id"]), InteractionOut.from_mongo(d)) for d in docs]

    if include_events and kind in (None, "", "meeting"):
        items += await _event_items(db, contact_id, from_, to, q, parsed, limit + 1)

    items.sort(key=lambda t: (t[0], t[1]), reverse=True)
    page = items[:limit]
    more = len(items) > limit
    next_cursor = encode_cursor(page[-1][0], page[-1][1]) if more and page else None
    return InteractionPage(items=[i for _, _, i in page], next_cursor=next_cursor)


async def shared_contact_groups(db: AsyncIOMotorDatabase) -> list[list[str]]:
    """Списки людей из взаимодействий и прошедших событий, где их двое и больше (для графа «Сеть»)."""
    shared: list[list[str]] = []
    two_plus = {"contact_ids.1": {"$exists": True}}
    async for doc in db[COLLECTION].find(two_plus, {"contact_ids": 1}):
        shared.append(list(doc.get("contact_ids") or []))
    async for doc in db[events_repo.COLLECTION].find({**two_plus, "start": {"$lte": _utcnow()}}, {"contact_ids": 1}):
        shared.append(list(doc.get("contact_ids") or []))
    return shared


async def _event_items(
    db: AsyncIOMotorDatabase,
    contact_id: Optional[str],
    from_: Optional[datetime],
    to: Optional[datetime],
    q: Optional[str],
    cursor: Optional[tuple],
    limit: int,
) -> list[tuple[datetime, str, InteractionOut]]:
    """Прошедшие события, привязанные к людям, в виде встреч (только чтение)."""
    clauses = _time_filters("start", from_, to, cursor)
    clauses.append({"start": {"$lte": _utcnow()}})
    clauses.append({"contact_ids": contact_id} if contact_id else {"contact_ids.0": {"$exists": True}})
    if q and q.strip():
        clauses.append({"$or": [{"title": _regex(q)}, {"location": _regex(q)}]})
    docs = (
        await db[events_repo.COLLECTION]
        .find({"$and": clauses})
        .sort([("start", -1), ("_id", -1)])
        .limit(limit)
        .to_list(length=limit)
    )
    return [(to_aware_utc(d["start"]), str(d["_id"]), InteractionOut.from_event(d)) for d in docs]
