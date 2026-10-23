"""
Репозиторий вопросов к человеку (коллекция questions).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.question import QuestionCreate, QuestionOut, QuestionStatus, QuestionUpdate

COLLECTION = "questions"
CONTACTS = "contacts"


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
    """Имена контактов одним запросом (без N+1)."""
    oids = [oid for oid in (_parse_oid(c) for c in contact_ids) if oid is not None]
    if not oids:
        return {}
    docs = await db[CONTACTS].find(
        {"_id": {"$in": oids}}, {"first_name": 1, "last_name": 1}
    ).to_list(length=len(oids))
    return {str(d["_id"]): _full_name(d) for d in docs}


async def _with_name(db: AsyncIOMotorDatabase, doc: dict) -> QuestionOut:
    names = await _contact_names(db, {doc["contact_id"]})
    return QuestionOut.from_mongo(doc, names.get(doc["contact_id"], ""))


async def create_question(db: AsyncIOMotorDatabase, data: QuestionCreate) -> QuestionOut:
    now = _utcnow()
    doc = {
        **data.model_dump(),
        "status": "open",
        "answer": "",
        "answered_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[COLLECTION].insert_one(doc)
    return await _with_name(db, {**doc, "_id": result.inserted_id})


async def list_questions(
    db: AsyncIOMotorDatabase,
    status: Optional[QuestionStatus] = None,
    contact_id: Optional[str] = None,
    limit: int = 200,
) -> list[QuestionOut]:
    query: dict = {}
    if status:
        query["status"] = status
    if contact_id:
        query["contact_id"] = contact_id
    docs = await db[COLLECTION].find(query).sort("created_at", 1).limit(limit).to_list(length=limit)
    names = await _contact_names(db, {d["contact_id"] for d in docs})
    return [QuestionOut.from_mongo(d, names.get(d["contact_id"], "")) for d in docs]


async def update_question(
    db: AsyncIOMotorDatabase, question_id: str, data: QuestionUpdate
) -> Optional[QuestionOut]:
    oid = _parse_oid(question_id)
    if oid is None:
        return None
    changes = data.model_dump(exclude_unset=True)
    if "status" in changes:
        changes["answered_at"] = _utcnow() if changes["status"] == "answered" else None
    changes["updated_at"] = _utcnow()
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    return await _with_name(db, doc) if doc else None


async def delete_question(db: AsyncIOMotorDatabase, question_id: str) -> bool:
    oid = _parse_oid(question_id)
    if oid is None:
        return False
    result = await db[COLLECTION].delete_one({"_id": oid})
    return result.deleted_count == 1


async def delete_for_contact(db: AsyncIOMotorDatabase, contact_id: str) -> int:
    result = await db[COLLECTION].delete_many({"contact_id": contact_id})
    return result.deleted_count


async def open_counts(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """{contact_id: число открытых вопросов}."""
    rows = await db[COLLECTION].aggregate(
        [{"$match": {"status": "open"}}, {"$group": {"_id": "$contact_id", "n": {"$sum": 1}}}]
    ).to_list(length=None)
    return {row["_id"]: row["n"] for row in rows}
