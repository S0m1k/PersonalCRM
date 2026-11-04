"""
Репозиторий контактов — async CRUD через motor (MongoDB).

Все методы принимают объект базы данных явно (AsyncIOMotorDatabase),
что позволяет подменять его в тестах (mongomock-motor).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.contact import ContactCreate, ContactOut, ContactUpdate, Phone
from ..services import phones

COLLECTION = "contacts"

# Поля, которые можно очистить явным null в PATCH (у остальных None означает «не менять»)
NULLABLE_FIELDS = ("first_met_at", "location", "importance", "closeness")

# sort= в списке контактов → ключи сортировки Mongo
SORTS: dict[str, list[tuple[str, int]]] = {
    "last_interaction": [("last_interaction_at", -1), ("updated_at", -1)],
    "name": [("first_name", 1), ("last_name", 1)],
    "created": [("created_at", -1)],
    "importance": [("importance", -1), ("updated_at", -1)],
}


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


async def get_contacts_by_ids(db: AsyncIOMotorDatabase, contact_ids: list[str]) -> list[ContactOut]:
    """Несколько контактов одним запросом; невалидные и несуществующие id пропускаются."""
    oids = [oid for oid in (_parse_oid(c) for c in contact_ids) if oid is not None]
    if not oids:
        return []
    docs = await db[COLLECTION].find({"_id": {"$in": oids}}).to_list(length=len(oids))
    return [ContactOut.from_mongo(d) for d in docs]


def build_query(
    q: Optional[str] = None,
    category: Optional[str] = None,
    priority: Optional[str] = None,
    template_id: Optional[str] = None,
    tag: Optional[str] = None,
    group_id: Optional[str] = None,
    has_location: Optional[bool] = None,
    has_frequency: Optional[bool] = None,
    has_priority: Optional[bool] = None,
    has_birthday: Optional[bool] = None,
    has_place: Optional[bool] = None,
    source: Optional[str] = None,
    inactive_days: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Фильтр Mongo для списка контактов; условия соединяются через $and."""
    clauses: list[dict] = []

    if q:
        # Поиск по нескольким полям через $or + $regex.
        # re.escape — чтобы спецсимволы (например "+" в телефоне) трактовались
        # буквально, а не как regex; заодно закрывает regex-инъекцию.
        pattern = {"$regex": re.escape(q), "$options": "i"}
        any_of: list[dict] = [
            {"first_name": pattern},
            {"last_name": pattern},
            {"company": pattern},
            {"emails.value": pattern},
            {"phones.value": pattern},
        ]
        # Номер в любой записи: 89215535333 найдёт и «+7 921 553-53-33»
        phone_pattern = phones.search_pattern(q)
        if phone_pattern:
            any_of.append({"phones.normalized": {"$regex": phone_pattern}})
        clauses.append({"$or": any_of})

    if category:
        clauses.append({"category": category})
    if priority:
        clauses.append({"priority": priority})
    if template_id:
        clauses.append({"template_id": template_id})
    if tag:
        clauses.append({"tags": {"$regex": f"^{re.escape(tag.strip())}$", "$options": "i"}})
    if group_id:
        clauses.append({"group_ids": group_id})
    if source:
        clauses.append({"$or": [{"source": source}, {"sources": source}]})

    if has_location is True:
        clauses.append({"location": {"$ne": None}})
    elif has_location is False:
        clauses.append({"location": None})

    if has_frequency is True:
        clauses.append({"keep_in_touch.frequency_days": {"$ne": None}})
    elif has_frequency is False:
        clauses.append({"keep_in_touch.frequency_days": None})

    # Приоритет не задан — пустая строка или поля нет; «none» («Нет») — выбранное значение
    if has_priority is True:
        clauses.append({"priority": {"$nin": ["", None]}})
    elif has_priority is False:
        clauses.append({"priority": {"$in": ["", None]}})

    if has_birthday is True:
        clauses.append({"birthday": {"$nin": ["", None]}})
    elif has_birthday is False:
        clauses.append({"birthday": {"$in": ["", None]}})

    # «Место» — адрес, город или метка координат
    place_fields = ({"address": {"$nin": ["", None]}}, {"city": {"$nin": ["", None]}}, {"location": {"$ne": None}})
    if has_place is True:
        clauses.append({"$or": list(place_fields)})
    elif has_place is False:
        clauses.append({"address": {"$in": ["", None]}})
        clauses.append({"city": {"$in": ["", None]}})
        clauses.append({"location": None})

    if inactive_days is not None:
        threshold = (now or _utcnow()) - timedelta(days=inactive_days)
        clauses.append({"$or": [{"last_interaction_at": None}, {"last_interaction_at": {"$lt": threshold}}]})

    if not clauses:
        return {}
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


async def list_contacts(
    db: AsyncIOMotorDatabase,
    sort: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    **filters,
) -> list[ContactOut]:
    """
    Список контактов с поиском и фильтрацией (параметры фильтров — см. build_query).

    - q: поиск по имени, фамилии, компании, email, телефону (без учёта регистра;
      номер сравнивается по ключу из services/phones.py, формат записи не важен)
    - sort: last_interaction | name | created | importance (по умолчанию — по updated_at)
    - skip / limit: пагинация
    """
    cursor = (
        db[COLLECTION]
        .find(build_query(**filters))
        .sort(SORTS.get(sort or "", [("updated_at", -1)]))
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)
    return [ContactOut.from_mongo(doc) for doc in docs]


async def count_contacts(db: AsyncIOMotorDatabase, **filters) -> int:
    """Сколько контактов подходит под те же фильтры, что и в list_contacts."""
    return await db[COLLECTION].count_documents(build_query(**filters))


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
    # Явный null очищает только «обнуляемые» поля
    for name in NULLABLE_FIELDS:
        if name in data.model_fields_set and getattr(data, name) is None:
            changes[name] = None
    if not changes:
        # Нечего обновлять — вернём текущее состояние
        return await get_contact_by_id(db, contact_id)

    changes["updated_at"] = _utcnow()

    # "" в PATCH означает «снять шаблон»
    if changes.get("template_id") == "":
        changes["template_id"] = None

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


async def backfill_phone_keys(db: AsyncIOMotorDatabase) -> int:
    """
    Дописать Phone.normalized телефонам, сохранённым до его появления (иначе поиск
    по номеру их не найдёт). Номера и updated_at не меняются — синхронизация этого не видит.
    Возвращает число исправленных контактов; повторный запуск ничего не делает.
    """
    fixed = 0
    cursor = db[COLLECTION].find({"phones": {"$elemMatch": {"normalized": {"$exists": False}}}}, {"phones": 1})
    async for doc in cursor:
        phones = [Phone(**p).model_dump() for p in doc.get("phones") or [] if p.get("value")]
        await db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"phones": phones}})
        fixed += 1
    return fixed


# ---------------------------------------------------------------------------
# Sprint 11: служебные операции над контактами
# ---------------------------------------------------------------------------


async def set_last_interaction(db: AsyncIOMotorDatabase, contact_id: str, value: Optional[datetime]) -> None:
    """
    Записать last_interaction_at. updated_at не трогаем: это служебное значение,
    синхронизацию с провайдерами оно не запускает.
    """
    oid = _parse_oid(contact_id)
    if oid is not None:
        await db[COLLECTION].update_one({"_id": oid}, {"$set": {"last_interaction_at": value}})


async def remove_group(db: AsyncIOMotorDatabase, group_id: str) -> int:
    """Группа удалена — убрать её id у всех контактов. Возвращает число затронутых контактов."""
    result = await db[COLLECTION].update_many({"group_ids": group_id}, {"$pull": {"group_ids": group_id}})
    return result.modified_count


async def count_by_group(db: AsyncIOMotorDatabase) -> dict[str, int]:
    """{group_id: число контактов}."""
    counts: dict[str, int] = {}
    async for doc in db[COLLECTION].find({"group_ids.0": {"$exists": True}}, {"group_ids": 1}):
        for gid in doc.get("group_ids") or []:
            counts[gid] = counts.get(gid, 0) + 1
    return counts


async def tag_counts(db: AsyncIOMotorDatabase) -> list[dict]:
    """Теги с числом контактов; регистр — самое частое написание, сортировка по числу и имени."""
    by_key: dict[str, dict] = {}
    async for doc in db[COLLECTION].find({"tags.0": {"$exists": True}}, {"tags": 1}):
        for tag in doc.get("tags") or []:
            entry = by_key.setdefault(tag.casefold(), {"spellings": {}, "count": 0})
            entry["count"] += 1
            entry["spellings"][tag] = entry["spellings"].get(tag, 0) + 1
    result = [
        {"tag": max(e["spellings"], key=lambda t: (e["spellings"][t], t)), "count": e["count"]}
        for e in by_key.values()
    ]
    return sorted(result, key=lambda r: (-r["count"], r["tag"].casefold()))


async def rewrite_tag(db: AsyncIOMotorDatabase, old: str, new: Optional[str]) -> int:
    """
    Переименовать / слить тег (new) или удалить его у всех контактов (new=None).
    Совпадение без учёта регистра; результат нормализуется как обычный список тегов.
    Возвращает число изменённых контактов.
    """
    from ..models.contact import normalize_labels

    key = old.strip().casefold()
    changed = 0
    async for doc in db[COLLECTION].find({"tags.0": {"$exists": True}}, {"tags": 1}):
        tags = doc.get("tags") or []
        if not any(t.casefold() == key for t in tags):
            continue
        rewritten = [new if t.casefold() == key else t for t in tags]
        if new is None:
            rewritten = [t for t in tags if t.casefold() != key]
        await db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"tags": normalize_labels(rewritten)}})
        changed += 1
    return changed
