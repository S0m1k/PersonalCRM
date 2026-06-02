"""
Репозиторий контактов — async CRUD через motor (MongoDB).

Все методы принимают объект базы данных явно (AsyncIOMotorDatabase),
что позволяет подменять его в тестах (mongomock-motor).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.contact import ContactCreate, ContactOut, ContactUpdate

COLLECTION = "contacts"


def _utcnow() -> datetime:
    """Текущее UTC-время с таймзоной."""
    return datetime.now(timezone.utc)


def _parse_oid(contact_id: str) -> Optional[ObjectId]:
    """Конвертация строки в ObjectId; при невалидном ID возвращает None."""
    try:
        return ObjectId(contact_id)
    except (InvalidId, TypeError):
        return None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_contact(db: AsyncIOMotorDatabase, data: ContactCreate) -> ContactOut:
    """
    Создать новый контакт. Устанавливает created_at и updated_at.
    Возвращает ContactOut с присвоенным id.
    """
    now = _utcnow()

    # Сериализуем Pydantic → dict, исключая None-значения верхнего уровня
    doc = data.model_dump(mode="python")
    doc["created_at"] = now
    doc["updated_at"] = now

    # sources: если пусто и source задан — инициализируем
    if not doc.get("sources") and doc.get("source"):
        doc["sources"] = [doc["source"]]

    # ExternalIds → dict для Mongo
    if hasattr(doc.get("external_ids"), "model_dump"):
        doc["external_ids"] = doc["external_ids"].model_dump()

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return ContactOut.from_mongo(doc)


async def get_contact_by_id(
    db: AsyncIOMotorDatabase, contact_id: str
) -> Optional[ContactOut]:
    """
    Получить контакт по ID.
    Возвращает None если ID невалидный или контакт не найден.
    """
    oid = _parse_oid(contact_id)
    if oid is None:
        return None

    doc = await db[COLLECTION].find_one({"_id": oid})
    if doc is None:
        return None
    return ContactOut.from_mongo(doc)


async def list_contacts(
    db: AsyncIOMotorDatabase,
    q: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ContactOut]:
    """
    Список контактов с поиском и фильтрацией.

    - q: поиск по имени, фамилии, компании, email, телефону (регексп, без учёта регистра)
    - category / priority: точная фильтрация по полю
    - skip / limit: пагинация
    """
    query: dict = {}

    if q:
        # Поиск по нескольким полям через $or + $regex.
        # re.escape — чтобы спецсимволы (например "+" в телефоне) трактовались
        # буквально, а не как regex; заодно закрывает regex-инъекцию.
        pattern = {"$regex": re.escape(q), "$options": "i"}
        query["$or"] = [
            {"first_name": pattern},
            {"last_name": pattern},
            {"company": pattern},
            {"emails.value": pattern},
            {"phones.value": pattern},
        ]

    if category:
        query["category"] = category

    if priority:
        query["priority"] = priority

    cursor = (
        db[COLLECTION]
        .find(query)
        .sort("updated_at", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [ContactOut.from_mongo(doc) for doc in docs]


async def update_contact(
    db: AsyncIOMotorDatabase,
    contact_id: str,
    data: ContactUpdate,
) -> Optional[ContactOut]:
    """
    Частичное обновление контакта (PATCH-семантика).
    Обновляет только те поля, которые явно переданы (не None).
    Возвращает None если ID невалидный или контакт не найден.
    """
    oid = _parse_oid(contact_id)
    if oid is None:
        return None

    # Берём только явно переданные поля (exclude_none=True)
    changes = data.model_dump(mode="python", exclude_none=True)
    if not changes:
        # Нечего обновлять — вернём текущее состояние
        return await get_contact_by_id(db, contact_id)

    changes["updated_at"] = _utcnow()

    # ExternalIds → dict
    if hasattr(changes.get("external_ids"), "model_dump"):
        changes["external_ids"] = changes["external_ids"].model_dump()

    result = await db[COLLECTION].find_one_and_update(
        {"_id": oid},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        return None
    return ContactOut.from_mongo(result)


async def delete_contact(db: AsyncIOMotorDatabase, contact_id: str) -> bool:
    """
    Удалить контакт по ID.
    Возвращает True если удалён, False если не найден или ID невалидный.
    """
    oid = _parse_oid(contact_id)
    if oid is None:
        return False

    result = await db[COLLECTION].delete_one({"_id": oid})
    return result.deleted_count == 1
