"""
Репозиторий напоминаний (коллекция reminders).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.reminder import ReminderCreate, ReminderOut, ReminderStatus, ReminderUpdate
from ..services.reminders import next_due_date

COLLECTION = "reminders"
CONTACTS = "contacts"
DEFAULT_LIMIT = 500
_SORT = [("due_date", 1), ("due_time", 1), ("created_at", 1)]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _full_name(doc: dict) -> str:
    return " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip()


async def _contact_names(db: AsyncIOMotorDatabase, contact_ids: set[str]) -> dict[str, str]:
    oids = [oid for oid in (_parse_oid(c) for c in contact_ids if c) if oid is not None]
    if not oids:
        return {}
    docs = await db[CONTACTS].find({"_id": {"$in": oids}}, {"first_name": 1, "last_name": 1}).to_list(length=len(oids))
    return {str(d["_id"]): _full_name(d) for d in docs}


async def _to_out(db: AsyncIOMotorDatabase, docs: list[dict]) -> list[ReminderOut]:
    names = await _contact_names(db, {d.get("contact_id") for d in docs if d.get("contact_id")})
    return [ReminderOut.from_mongo(d, names.get(d.get("contact_id") or "", "")) for d in docs]


async def create_reminder(db: AsyncIOMotorDatabase, data: ReminderCreate) -> ReminderOut:
    doc = {**data.model_dump(), "done_at": None, "created_at": _utcnow()}
    result = await db[COLLECTION].insert_one(doc)
    return (await _to_out(db, [{**doc, "_id": result.inserted_id}]))[0]


async def list_reminders(
    db: AsyncIOMotorDatabase,
    status: ReminderStatus = "all",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    contact_id: Optional[str] = None,
    limit: int = DEFAULT_LIMIT,
) -> list[ReminderOut]:
    query: dict = {}
    if status == "open":
        query["done_at"] = None
    elif status == "done":
        query["done_at"] = {"$ne": None}
    if contact_id:
        query["contact_id"] = contact_id
    due: dict = {}
    if date_from:
        due["$gte"] = date_from
    if date_to:
        due["$lte"] = date_to
    if due:
        query["due_date"] = due
    docs = await db[COLLECTION].find(query).sort(_SORT).limit(limit).to_list(length=limit)
    return await _to_out(db, docs)


async def update_reminder(db: AsyncIOMotorDatabase, reminder_id: str, data: ReminderUpdate) -> Optional[ReminderOut]:
    oid = _parse_oid(reminder_id)
    if oid is None:
        return None
    changes = data.model_dump(exclude_unset=True)
    # обязательные поля нельзя занулить
    changes = {k: v for k, v in changes.items() if v is not None or k in ("contact_id", "due_time")}
    if not changes:
        doc = await db[COLLECTION].find_one({"_id": oid})
    else:
        doc = await db[COLLECTION].find_one_and_update(
            {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
        )
    return (await _to_out(db, [doc]))[0] if doc else None


async def mark_done(db: AsyncIOMotorDatabase, reminder_id: str) -> Optional[ReminderOut]:
    """Отмечает выполненным; для повторяющегося создаёт следующее. Повторный вызов ничего не дублирует."""
    oid = _parse_oid(reminder_id)
    if oid is None:
        return None
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": oid, "done_at": None}, {"$set": {"done_at": _utcnow()}}, return_document=ReturnDocument.AFTER
    )
    if doc is None:  # нет такого или уже выполнено
        existing = await db[COLLECTION].find_one({"_id": oid})
        return (await _to_out(db, [existing]))[0] if existing else None
    following = next_due_date(date.fromisoformat(doc["due_date"]), doc.get("repeat", "none"))
    if following is not None:
        await db[COLLECTION].insert_one(
            {
                "contact_id": doc.get("contact_id"),
                "title": doc["title"],
                "note": doc.get("note", ""),
                "due_date": following.isoformat(),
                "due_time": doc.get("due_time"),
                "repeat": doc["repeat"],
                "done_at": None,
                "created_at": _utcnow(),
            }
        )
    return (await _to_out(db, [doc]))[0]


async def delete_reminder(db: AsyncIOMotorDatabase, reminder_id: str) -> bool:
    oid = _parse_oid(reminder_id)
    if oid is None:
        return False
    result = await db[COLLECTION].delete_one({"_id": oid})
    return result.deleted_count == 1


async def delete_for_contact(db: AsyncIOMotorDatabase, contact_id: str) -> int:
    result = await db[COLLECTION].delete_many({"contact_id": contact_id})
    return result.deleted_count
