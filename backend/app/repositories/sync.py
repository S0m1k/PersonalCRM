"""
Репозиторий sync_connections и sync_log.

Токены OAuth хранятся зашифрованными (crypto.encrypt / crypto.decrypt).
Все методы принимают db явно для подмены в тестах.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from ..crypto import decrypt, encrypt
from ..models.sync import SyncConnection, SyncLog, SyncStats, SyncError

CONN_COLLECTION = "sync_connections"
LOG_COLLECTION = "sync_log"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_oid(id_str: str) -> Optional[ObjectId]:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None


# ---------------------------------------------------------------------------
# Helpers: шифрование на запись, расшифровка на чтение
# ---------------------------------------------------------------------------


def _encrypt_tokens(doc: dict) -> dict:
    """Зашифровать access_token и refresh_token перед записью в БД."""
    if "access_token" in doc:
        doc["access_token_enc"] = encrypt(doc.pop("access_token"))
    if "refresh_token" in doc and doc["refresh_token"] is not None:
        doc["refresh_token_enc"] = encrypt(doc.pop("refresh_token"))
    elif "refresh_token" in doc:
        doc["refresh_token_enc"] = None
        doc.pop("refresh_token")
    return doc


def _decrypt_tokens(conn: SyncConnection) -> tuple[str, Optional[str]]:
    """
    Расшифровать токены из SyncConnection.
    Возвращает (access_token, refresh_token).
    """
    access_token = decrypt(conn.access_token_enc)
    refresh_token = decrypt(conn.refresh_token_enc) if conn.refresh_token_enc else None
    return access_token, refresh_token


# ---------------------------------------------------------------------------
# SyncConnection CRUD
# ---------------------------------------------------------------------------


async def create_connection(
    db: AsyncIOMotorDatabase,
    *,
    provider: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    token_expires_at: Optional[datetime] = None,
    sync_contacts: bool = True,
    sync_calendar: bool = False,
) -> SyncConnection:
    """Создать новое подключение с зашифрованными токенами."""
    now = _utcnow()
    doc: dict = {
        "provider": provider,
        "access_token": access_token,
        "token_expires_at": token_expires_at,
        "sync_contacts": sync_contacts,
        "sync_calendar": sync_calendar,
        "contacts_delta_link": None,
        "contacts_sync_token": None,
        "contacts_last_sync": None,
        "calendar_last_sync": None,
        "webhook_subscription_id": None,
        "webhook_expires_at": None,
        "created_at": now,
        "updated_at": now,
    }
    if refresh_token is not None:
        doc["refresh_token"] = refresh_token
    _encrypt_tokens(doc)
    result = await db[CONN_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return SyncConnection.from_mongo(doc)


async def get_connection(
    db: AsyncIOMotorDatabase, connection_id: str
) -> Optional[SyncConnection]:
    """Получить подключение по ID."""
    oid = _parse_oid(connection_id)
    if oid is None:
        return None
    doc = await db[CONN_COLLECTION].find_one({"_id": oid})
    if doc is None:
        return None
    return SyncConnection.from_mongo(doc)


async def list_connections(db: AsyncIOMotorDatabase) -> list[SyncConnection]:
    """Все подключения."""
    docs = await db[CONN_COLLECTION].find({}).to_list(length=100)
    return [SyncConnection.from_mongo(doc) for doc in docs]


async def update_connection(
    db: AsyncIOMotorDatabase,
    connection_id: str,
    **fields,
) -> Optional[SyncConnection]:
    """
    Обновить произвольные поля подключения.
    Если передаются access_token / refresh_token — шифруем на месте.
    """
    oid = _parse_oid(connection_id)
    if oid is None:
        return None

    changes = dict(fields)
    _encrypt_tokens(changes)
    changes["updated_at"] = _utcnow()

    result = await db[CONN_COLLECTION].find_one_and_update(
        {"_id": oid},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        return None
    return SyncConnection.from_mongo(result)


async def delete_connection(db: AsyncIOMotorDatabase, connection_id: str) -> bool:
    """Удалить подключение. Возвращает True при успехе."""
    oid = _parse_oid(connection_id)
    if oid is None:
        return False
    result = await db[CONN_COLLECTION].delete_one({"_id": oid})
    return result.deleted_count == 1


def get_decrypted_tokens(conn: SyncConnection) -> tuple[str, Optional[str]]:
    """
    Публичный хелпер: расшифровать и вернуть (access_token, refresh_token).
    Вызывается из sync-движков, которые передают токены в httpx.
    """
    return _decrypt_tokens(conn)


# ---------------------------------------------------------------------------
# SyncLog CRUD
# ---------------------------------------------------------------------------


async def create_log(
    db: AsyncIOMotorDatabase,
    *,
    connection_id: str,
    type: str,
    action: str,
    stats: Optional[SyncStats] = None,
    errors: Optional[list[SyncError]] = None,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
) -> SyncLog:
    """Создать запись в лог синхронизации."""
    now = _utcnow()
    doc: dict = {
        "connection_id": connection_id,
        "type": type,
        "action": action,
        "stats": (stats or SyncStats()).model_dump(),
        "errors": [e.model_dump() for e in (errors or [])],
        "started_at": started_at or now,
        "completed_at": completed_at,
    }
    result = await db[LOG_COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return SyncLog.from_mongo(doc)


async def update_log(
    db: AsyncIOMotorDatabase,
    log_id: str,
    *,
    stats: Optional[SyncStats] = None,
    errors: Optional[list[SyncError]] = None,
    completed_at: Optional[datetime] = None,
) -> Optional[SyncLog]:
    """Обновить запись лога (как правило — после завершения sync)."""
    oid = _parse_oid(log_id)
    if oid is None:
        return None
    changes: dict = {"completed_at": completed_at or _utcnow()}
    if stats is not None:
        changes["stats"] = stats.model_dump()
    if errors is not None:
        changes["errors"] = [e.model_dump() for e in errors]
    result = await db[LOG_COLLECTION].find_one_and_update(
        {"_id": oid},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        return None
    return SyncLog.from_mongo(result)


async def list_logs(
    db: AsyncIOMotorDatabase,
    connection_id: Optional[str] = None,
    limit: int = 50,
) -> list[SyncLog]:
    """История лога, опционально отфильтрованная по connection_id."""
    query: dict = {}
    if connection_id:
        query["connection_id"] = connection_id
    docs = await (
        db[LOG_COLLECTION]
        .find(query)
        .sort("started_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )
    return [SyncLog.from_mongo(doc) for doc in docs]
