"""
Репозиторий пользователей (коллекция users в системной базе settings.db_name).

Хеши паролей наружу отдаёт только get_auth_doc — для проверки при входе.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from ..config import settings
from ..models.user import User, normalize_login

COLLECTION = "users"


class EmailTakenError(Exception):
    """Пользователь с таким email уже есть."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def tenant_db_name(user_oid: ObjectId) -> str:
    """База с данными пользователя: personalcrm_u_<id>."""
    return f"{settings.db_name}_u_{user_oid}"


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """Уникальный email. Идемпотентно: MongoDB не пересоздаёт существующий индекс."""
    await db[COLLECTION].create_index("email", unique=True)


async def count_users(db: AsyncIOMotorDatabase) -> int:
    return await db[COLLECTION].count_documents({})


async def create_user(
    db: AsyncIOMotorDatabase,
    *,
    email: str,
    password_hash: str,
    name: str = "",
    db_name: Optional[str] = None,
    is_admin: bool = False,
    carddav_secret: Optional[str] = None,
) -> User:
    """Создать пользователя. db_name=None — новая отдельная база."""
    # Индекс — здесь, а не только при старте: MongoDB могла быть недоступна в момент запуска
    await ensure_indexes(db)
    email = normalize_login(email)
    if await db[COLLECTION].find_one({"email": email}, {"_id": 1}):
        raise EmailTakenError(email)
    oid = ObjectId()
    doc = {
        "_id": oid,
        "email": email,
        "name": name,
        "password_hash": password_hash,
        "db_name": db_name or tenant_db_name(oid),
        "is_admin": is_admin,
        "carddav_secret": carddav_secret,
        "token_version": 0,
        "created_at": _utcnow(),
    }
    try:
        await db[COLLECTION].insert_one(doc)
    except DuplicateKeyError:
        # Гонка двух регистраций с одним email — уникальный индекс не пустил вторую
        raise EmailTakenError(email) from None
    return User.from_mongo(doc)


async def get_user(db: AsyncIOMotorDatabase, user_id: str) -> Optional[User]:
    oid = _parse_oid(user_id)
    if oid is None:
        return None
    doc = await db[COLLECTION].find_one({"_id": oid})
    return User.from_mongo(doc) if doc else None


async def get_auth_doc(db: AsyncIOMotorDatabase, email: str) -> Optional[dict]:
    """Документ с хешами — только для проверки пароля."""
    return await db[COLLECTION].find_one({"email": normalize_login(email)})


async def list_users(db: AsyncIOMotorDatabase) -> list[User]:
    docs = await db[COLLECTION].find().sort("created_at", 1).to_list(length=None)
    return [User.from_mongo(d) for d in docs]


async def set_password_hash(db: AsyncIOMotorDatabase, user_id: str, password_hash: str) -> int:
    """Сменить пароль и отозвать все выданные токены. Возвращает новую версию токенов."""
    doc = await db[COLLECTION].find_one_and_update(
        {"_id": _parse_oid(user_id)},
        {"$set": {"password_hash": password_hash}, "$inc": {"token_version": 1}},
        return_document=ReturnDocument.AFTER,
    )
    return doc.get("token_version", 0) if doc else 0


async def set_carddav_secret(db: AsyncIOMotorDatabase, user_id: str, secret: Optional[str]) -> None:
    await db[COLLECTION].update_one(
        {"_id": _parse_oid(user_id)}, {"$set": {"carddav_secret": secret}}
    )
