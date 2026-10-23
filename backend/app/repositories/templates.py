"""
Репозиторий шаблонов карточек (коллекция card_templates).

При первом обращении к пустой коллекции создаются встроенные шаблоны.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..models.template import FieldDef, TemplateCreate, TemplateOut, TemplateUpdate

COLLECTION = "card_templates"
CONTACTS = "contacts"

# Встроенные шаблоны: (имя, иконка lucide, [(ключ, подпись, тип, варианты)])
BUILTIN: list[tuple[str, str, list[tuple[str, str, str, list[str]]]]] = [
    ("Клиент", "briefcase", [
        ("stage", "Стадия", "select", ["Лид", "Переговоры", "Клиент", "Бывший клиент"]),
        ("buys", "Что покупает", "text", []),
        ("budget", "Бюджет", "number", []),
        ("website", "Сайт", "url", []),
    ]),
    ("Партнёр", "handshake", [
        ("industry", "Сфера", "text", []),
        ("useful_for", "Чем полезен", "longtext", []),
        ("projects", "Совместные проекты", "longtext", []),
        ("website", "Сайт", "url", []),
    ]),
    ("Друг", "smile", [
        ("family", "Семья", "longtext", []),
        ("interests", "Интересы", "text", []),
        ("met_how", "Как познакомились", "text", []),
        ("gifts", "Идеи подарков", "longtext", []),
    ]),
    ("Родственник", "house", [
        ("relation", "Кем приходится", "text", []),
        ("family", "Семья", "longtext", []),
        ("interests", "Интересы", "text", []),
        ("gifts", "Идеи подарков", "longtext", []),
    ]),
    ("Сотрудник", "id-card", [
        ("department", "Отдел", "text", []),
        ("hired", "Дата найма", "date", []),
        ("manager", "Руководитель", "text", []),
        ("skills", "Сильные стороны", "text", []),
    ]),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_oid(template_id: str) -> Optional[ObjectId]:
    try:
        return ObjectId(template_id)
    except (InvalidId, TypeError):
        return None


def _with_keys(fields: list[FieldDef]) -> list[dict]:
    """Выдать ключи новым полям, не трогая существующие."""
    used = {f.key for f in fields if f.key}
    result = []
    for field in fields:
        key = field.key
        while not key or (key in used and key != field.key):
            key = f"f_{secrets.token_hex(3)}"
        used.add(key)
        result.append({**field.model_dump(), "key": key})
    return result


async def _seed_builtin(db: AsyncIOMotorDatabase) -> None:
    now = _utcnow()
    docs = [
        {
            "name": name,
            "icon": icon,
            "fields": [
                {"key": key, "label": label, "type": ftype, "options": options}
                for key, label, ftype, options in fields
            ],
            "builtin": True,
            "position": position,
            "created_at": now,
            "updated_at": now,
        }
        for position, (name, icon, fields) in enumerate(BUILTIN)
    ]
    await db[COLLECTION].insert_many(docs)


async def list_templates(db: AsyncIOMotorDatabase) -> list[TemplateOut]:
    if await db[COLLECTION].count_documents({}, limit=1) == 0:
        await _seed_builtin(db)
    docs = await db[COLLECTION].find().sort([("position", 1), ("created_at", 1)]).to_list(length=200)
    return [TemplateOut.from_mongo(d) for d in docs]


async def get_template(db: AsyncIOMotorDatabase, template_id: str) -> Optional[TemplateOut]:
    oid = _parse_oid(template_id)
    if oid is None:
        return None
    doc = await db[COLLECTION].find_one({"_id": oid})
    return TemplateOut.from_mongo(doc) if doc else None


async def create_template(db: AsyncIOMotorDatabase, data: TemplateCreate) -> TemplateOut:
    now = _utcnow()
    doc = {
        "name": data.name.strip(),
        "icon": data.icon,
        "fields": _with_keys(data.fields),
        "builtin": False,
        "position": 1000,
        "created_at": now,
        "updated_at": now,
    }
    result = await db[COLLECTION].insert_one(doc)
    return TemplateOut.from_mongo({**doc, "_id": result.inserted_id})


async def update_template(
    db: AsyncIOMotorDatabase, template_id: str, data: TemplateUpdate
) -> Optional[TemplateOut]:
    oid = _parse_oid(template_id)
    if oid is None:
        return None
    changes: dict = {"updated_at": _utcnow()}
    if data.name is not None:
        changes["name"] = data.name.strip()
    if data.icon is not None:
        changes["icon"] = data.icon
    if data.fields is not None:
        changes["fields"] = _with_keys(data.fields)
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    return TemplateOut.from_mongo(doc) if doc else None


async def count_usage(db: AsyncIOMotorDatabase, template_id: str) -> int:
    return await db[CONTACTS].count_documents({"template_id": template_id})


async def delete_template(db: AsyncIOMotorDatabase, template_id: str) -> bool:
    oid = _parse_oid(template_id)
    if oid is None:
        return False
    result = await db[COLLECTION].delete_one({"_id": oid})
    return result.deleted_count == 1
