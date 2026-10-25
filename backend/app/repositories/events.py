"""
Репозиторий событий календаря (коллекция events в базе пользователя).

Привязка к людям: contact_ids = (найденные по участникам − отвязанные вручную) ∪ привязанные вручную.
Ручной выбор хранится отдельно (manual_contact_ids / excluded_contact_ids), поэтому
повторная синхронизация с провайдером не отменяет его.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.event import Attendee, ContactBrief, EventOut, EventQuestion
from ..sync.dedup import normalize_phone

COLLECTION = "events"
CONTACTS = "contacts"
QUESTIONS = "questions"

LIST_LIMIT = 1000
# Телефоны сравниваем по последним 10 цифрам: «+7 900…» и «8 900…» — один номер
PHONE_TAIL = 10


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _full_name(doc: dict) -> str:
    return " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip()


def _phone_key(value: str) -> str:
    return normalize_phone(value)[-PHONE_TAIL:]


# ---------------------------------------------------------------------------
# Привязка к контактам
# ---------------------------------------------------------------------------


async def match_contacts(db: AsyncIOMotorDatabase, attendees: Iterable[Attendee]) -> list[str]:
    """id контактов, у которых совпал email или телефон с кем-то из участников."""
    attendees = list(attendees)
    emails = {a.email for a in attendees if a.email}
    phones = {_phone_key(a.phone) for a in attendees if a.phone and len(_phone_key(a.phone)) >= 7}
    found: list[str] = []
    if emails:
        # В контактах email может быть в любом регистре
        patterns = [{"emails.value": {"$regex": f"^{re.escape(e)}$", "$options": "i"}} for e in emails]
        docs = await db[CONTACTS].find({"$or": patterns}, {"_id": 1}).to_list(length=None)
        found.extend(str(d["_id"]) for d in docs)
    if phones:
        docs = await db[CONTACTS].find({"phones.0": {"$exists": True}}, {"phones": 1}).to_list(length=None)
        for doc in docs:
            if any(_phone_key(p.get("value", "")) in phones for p in doc.get("phones") or []):
                found.append(str(doc["_id"]))
    return list(dict.fromkeys(found))


async def existing_contact_ids(db: AsyncIOMotorDatabase, ids: Iterable[str]) -> list[str]:
    """Оставить только id существующих контактов (в порядке запроса)."""
    ids = list(dict.fromkeys(ids))
    oids = [oid for oid in (_parse_oid(i) for i in ids) if oid is not None]
    if not oids:
        return []
    docs = await db[CONTACTS].find({"_id": {"$in": oids}}, {"_id": 1}).to_list(length=len(oids))
    present = {str(d["_id"]) for d in docs}
    return [i for i in ids if i in present]


def combine_links(auto: list[str], manual: list[str], excluded: list[str]) -> list[str]:
    return list(dict.fromkeys([c for c in auto if c not in excluded] + manual))


def split_manual_choice(chosen: list[str], auto: list[str]) -> tuple[list[str], list[str]]:
    """Выбор пользователя → (привязанные вручную, отвязанные вручную) относительно найденных."""
    manual = [c for c in chosen if c not in auto]
    excluded = [c for c in auto if c not in chosen]
    return manual, excluded


# ---------------------------------------------------------------------------
# Обогащение: имена людей и открытые вопросы «на встрече»
# ---------------------------------------------------------------------------


async def _enrich(db: AsyncIOMotorDatabase, docs: list[dict]) -> list[EventOut]:
    contact_ids = {c for d in docs for c in d.get("contact_ids") or []}
    names: dict[str, str] = {}
    oids = [oid for oid in (_parse_oid(c) for c in contact_ids) if oid is not None]
    if oids:
        rows = await db[CONTACTS].find({"_id": {"$in": oids}}, {"first_name": 1, "last_name": 1}).to_list(
            length=len(oids)
        )
        names = {str(r["_id"]): _full_name(r) for r in rows}

    questions: dict[str, list[EventQuestion]] = {}
    if contact_ids:
        rows = await (
            db[QUESTIONS]
            .find({"status": "open", "ask_at": "next_meeting", "contact_id": {"$in": list(contact_ids)}})
            .sort("created_at", 1)
            .to_list(length=None)
        )
        for r in rows:
            questions.setdefault(r["contact_id"], []).append(
                EventQuestion(
                    id=str(r["_id"]),
                    contact_id=r["contact_id"],
                    contact_name=names.get(r["contact_id"], ""),
                    text=r.get("text", ""),
                )
            )

    result = []
    for doc in docs:
        linked = [c for c in doc.get("contact_ids") or [] if c in names]
        result.append(
            EventOut.from_mongo(
                doc,
                contact_ids=linked,
                contacts=[ContactBrief(id=c, name=names[c]) for c in linked],
                questions=[q for c in linked for q in questions.get(c, [])],
            )
        )
    return result


async def to_out(db: AsyncIOMotorDatabase, doc: dict) -> EventOut:
    return (await _enrich(db, [doc]))[0]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def insert_event(db: AsyncIOMotorDatabase, fields: dict) -> dict:
    now = _utcnow()
    doc = {
        "location": "",
        "description": "",
        "attendees": [],
        "contact_ids": [],
        "manual_contact_ids": [],
        "excluded_contact_ids": [],
        "push_questions": False,
        "source": "crm",
        "connection_id": None,
        "external_id": None,
        "etag": None,
        "web_link": "",
        **fields,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[COLLECTION].insert_one(doc)
    return {**doc, "_id": result.inserted_id}


async def get_event_doc(db: AsyncIOMotorDatabase, event_id: str) -> Optional[dict]:
    oid = _parse_oid(event_id)
    return await db[COLLECTION].find_one({"_id": oid}) if oid else None


async def find_external(db: AsyncIOMotorDatabase, connection_id: str, external_id: str) -> Optional[dict]:
    return await db[COLLECTION].find_one({"connection_id": connection_id, "external_id": external_id})


async def update_event_doc(db: AsyncIOMotorDatabase, event_id: str, changes: dict) -> Optional[dict]:
    oid = _parse_oid(event_id)
    if oid is None:
        return None
    return await db[COLLECTION].find_one_and_update(
        {"_id": oid},
        {"$set": {**changes, "updated_at": _utcnow()}},
        return_document=ReturnDocument.AFTER,
    )


async def delete_event(db: AsyncIOMotorDatabase, event_id: str) -> bool:
    oid = _parse_oid(event_id)
    if oid is None:
        return False
    return (await db[COLLECTION].delete_one({"_id": oid})).deleted_count == 1


async def delete_external(db: AsyncIOMotorDatabase, connection_id: str, external_id: str) -> bool:
    result = await db[COLLECTION].delete_one({"connection_id": connection_id, "external_id": external_id})
    return result.deleted_count == 1


async def delete_for_connection(db: AsyncIOMotorDatabase, connection_id: str) -> int:
    return (await db[COLLECTION].delete_many({"connection_id": connection_id})).deleted_count


async def list_events(
    db: AsyncIOMotorDatabase,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    contact_id: Optional[str] = None,
    limit: int = LIST_LIMIT,
) -> list[EventOut]:
    """События, пересекающиеся с [start, end), по возрастанию начала."""
    query: dict = {}
    if end is not None:
        query["start"] = {"$lt": end}
    if start is not None:
        query["end"] = {"$gt": start}
    if contact_id:
        query["contact_ids"] = contact_id
    docs = await db[COLLECTION].find(query).sort("start", 1).limit(limit).to_list(length=limit)
    return await _enrich(db, docs)


async def unlink_contact(db: AsyncIOMotorDatabase, contact_id: str) -> None:
    """Контакт удалён — убрать его из всех событий."""
    await db[COLLECTION].update_many(
        {"$or": [{"contact_ids": contact_id}, {"manual_contact_ids": contact_id}]},
        {"$pull": {"contact_ids": contact_id, "manual_contact_ids": contact_id, "excluded_contact_ids": contact_id}},
    )
