"""
Репозиторий сохранённых видов контактов (коллекция views в базе пользователя).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.view import ViewCreate, ViewOut, ViewUpdate

COLLECTION = "views"


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def list_views(db: AsyncIOMotorDatabase) -> list[ViewOut]:
    """Все виды в порядке создания."""
    docs = await db[COLLECTION].find({}).sort("created_at", 1).to_list(length=None)
    return [ViewOut.from_mongo(d) for d in docs]


async def get_view(db: AsyncIOMotorDatabase, view_id: str) -> Optional[ViewOut]:
    oid = _parse_oid(view_id)
    doc = await db[COLLECTION].find_one({"_id": oid}) if oid else None
    return ViewOut.from_mongo(doc) if doc else None


async def name_taken(db: AsyncIOMotorDatabase, name: str, exclude_id: Optional[str] = None) -> bool:
    """Вид с таким именем (без учёта регистра) уже есть."""
    key = name.strip().casefold()
    async for doc in db[COLLECTION].find({}, {"name": 1}):
        if str(doc["_id"]) != exclude_id and doc.get("name", "").casefold() == key:
            return True
    return False


async def create_view(db: AsyncIOMotorDatabase, data: ViewCreate) -> ViewOut:
    doc = {**data.model_dump(), "created_at": datetime.now(timezone.utc)}
    result = await db[COLLECTION].insert_one(doc)
    return ViewOut.from_mongo({**doc, "_id": result.inserted_id})


async def update_view(db: AsyncIOMotorDatabase, view_id: str, data: ViewUpdate) -> Optional[ViewOut]:
    oid = _parse_oid(view_id)
    if oid is None:
        return None
    changes = data.model_dump(exclude_none=True)
    if "sort" in data.model_fields_set and data.sort is None:
        changes["sort"] = None  # явный null сбрасывает сортировку
    if not changes:
        return await get_view(db, view_id)
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    return ViewOut.from_mongo(doc) if doc else None


async def delete_view(db: AsyncIOMotorDatabase, view_id: str) -> bool:
    oid = _parse_oid(view_id)
    if oid is None:
        return False
    return (await db[COLLECTION].delete_one({"_id": oid})).deleted_count == 1
