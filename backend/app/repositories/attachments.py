"""
Репозиторий вложений (коллекция attachments в базе пользователя).

Документ: contact_id, file_name, size, content_type, object_key, created_at.
Сами файлы лежат в S3 под object_key (app/storage.py).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

COLLECTION = "attachments"


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[COLLECTION].create_index([("contact_id", 1), ("created_at", -1)])


async def create(
    db: AsyncIOMotorDatabase,
    *,
    contact_id: str,
    file_name: str,
    size: int,
    content_type: str,
    object_key: str,
) -> dict:
    doc = {
        "contact_id": contact_id,
        "file_name": file_name,
        "size": size,
        "content_type": content_type,
        "object_key": object_key,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db[COLLECTION].insert_one(doc)
    return {**doc, "_id": result.inserted_id}


async def list_for_contact(db: AsyncIOMotorDatabase, contact_id: str) -> list[dict]:
    return await db[COLLECTION].find({"contact_id": contact_id}).sort("created_at", -1).to_list(length=None)


async def get(db: AsyncIOMotorDatabase, contact_id: str, attachment_id: str) -> Optional[dict]:
    oid = _parse_oid(attachment_id)
    if oid is None:
        return None
    return await db[COLLECTION].find_one({"_id": oid, "contact_id": contact_id})


async def delete(db: AsyncIOMotorDatabase, attachment_id: ObjectId) -> None:
    await db[COLLECTION].delete_one({"_id": attachment_id})


async def delete_for_contact(db: AsyncIOMotorDatabase, contact_id: str) -> list[str]:
    """Удалить метаданные вложений контакта. Вернуть ключи их объектов в S3."""
    docs = await db[COLLECTION].find({"contact_id": contact_id}, {"object_key": 1}).to_list(length=None)
    if docs:
        await db[COLLECTION].delete_many({"_id": {"$in": [d["_id"] for d in docs]}})
    return [d["object_key"] for d in docs]


async def total_size(db: AsyncIOMotorDatabase) -> int:
    """Сумма размеров всех вложений пользователя (для квоты)."""
    rows = await db[COLLECTION].aggregate([{"$group": {"_id": None, "total": {"$sum": "$size"}}}]).to_list(length=1)
    return int(rows[0]["total"]) if rows else 0
