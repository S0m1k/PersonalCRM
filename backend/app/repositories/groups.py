"""
Репозиторий групп контактов (коллекция groups в базе пользователя).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.group import GroupCreate, GroupOut, GroupUpdate
from . import contacts as contacts_repo

COLLECTION = "groups"


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def list_groups(db: AsyncIOMotorDatabase) -> list[GroupOut]:
    """Все группы по имени, с числом участников."""
    docs = await db[COLLECTION].find({}).sort("name", 1).to_list(length=None)
    counts = await contacts_repo.count_by_group(db)
    return [GroupOut.from_mongo(d, counts.get(str(d["_id"]), 0)) for d in docs]


async def get_group(db: AsyncIOMotorDatabase, group_id: str) -> Optional[GroupOut]:
    oid = _parse_oid(group_id)
    doc = await db[COLLECTION].find_one({"_id": oid}) if oid else None
    if doc is None:
        return None
    count = await db[contacts_repo.COLLECTION].count_documents({"group_ids": group_id})
    return GroupOut.from_mongo(doc, count)


async def name_taken(db: AsyncIOMotorDatabase, name: str, exclude_id: Optional[str] = None) -> bool:
    """Группа с таким именем (без учёта регистра) уже есть."""
    key = name.strip().casefold()
    async for doc in db[COLLECTION].find({}, {"name": 1}):
        if str(doc["_id"]) != exclude_id and doc.get("name", "").casefold() == key:
            return True
    return False


async def create_group(db: AsyncIOMotorDatabase, data: GroupCreate) -> GroupOut:
    doc = {**data.model_dump(), "created_at": datetime.now(timezone.utc)}
    result = await db[COLLECTION].insert_one(doc)
    return GroupOut.from_mongo({**doc, "_id": result.inserted_id})


async def update_group(db: AsyncIOMotorDatabase, group_id: str, data: GroupUpdate) -> Optional[GroupOut]:
    oid = _parse_oid(group_id)
    if oid is None:
        return None
    changes = data.model_dump(exclude_none=True)
    if changes:
        doc = await db[COLLECTION].find_one_and_update(
            {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
        )
        if doc is None:
            return None
    return await get_group(db, group_id)


async def delete_group(db: AsyncIOMotorDatabase, group_id: str) -> bool:
    """Удалить группу и убрать её id у всех контактов."""
    oid = _parse_oid(group_id)
    if oid is None:
        return False
    if (await db[COLLECTION].delete_one({"_id": oid})).deleted_count != 1:
        return False
    await contacts_repo.remove_group(db, group_id)
    return True


async def existing_group_ids(db: AsyncIOMotorDatabase, ids: list[str]) -> list[str]:
    """Оставить id существующих групп (в порядке запроса)."""
    oids = [oid for oid in (_parse_oid(i) for i in ids) if oid is not None]
    if not oids:
        return []
    docs = await db[COLLECTION].find({"_id": {"$in": oids}}, {"_id": 1}).to_list(length=len(oids))
    present = {str(d["_id"]) for d in docs}
    return [i for i in ids if i in present]


async def names_by_id(db: AsyncIOMotorDatabase, ids: list[str]) -> dict[str, str]:
    oids = [oid for oid in (_parse_oid(i) for i in ids) if oid is not None]
    if not oids:
        return {}
    docs = await db[COLLECTION].find({"_id": {"$in": oids}}, {"name": 1}).to_list(length=len(oids))
    return {str(d["_id"]): d.get("name", "") for d in docs}
