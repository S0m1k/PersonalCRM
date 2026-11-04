"""
Репозиторий чатов ИИ-помощника: коллекции chats и chat_messages в базе пользователя.

Чат: {title, created_at, updated_at, archived, summary, summary_upto}.
Сообщение: {chat_id, role, content, blocks, job_id, created_at}.
summary — сводка старых сообщений, summary_upto — сколько первых сообщений чата она покрывает.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import TypeAdapter
from pymongo import ReturnDocument

from ..models.chat import Block, ChatOut, MessageOut

CHATS = "chats"
MESSAGES = "chat_messages"
DEFAULT_TITLE = "Новый чат"
TITLE_FROM_MESSAGE = 60

_BLOCKS = TypeAdapter(list[Block])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _oid(value: str) -> Optional[ObjectId]:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value or "")


def chat_out(doc: dict) -> ChatOut:
    return ChatOut(
        id=str(doc["_id"]),
        title=doc.get("title") or DEFAULT_TITLE,
        created_at=_iso(doc.get("created_at")),
        updated_at=_iso(doc.get("updated_at")),
        archived=bool(doc.get("archived", False)),
        summary=doc.get("summary", ""),
        summary_upto=int(doc.get("summary_upto", 0)),
    )


def message_out(doc: dict) -> MessageOut:
    return MessageOut(
        id=str(doc["_id"]),
        chat_id=doc["chat_id"],
        role=doc["role"],
        content=doc.get("content", ""),
        blocks=doc.get("blocks") or [],
        job_id=doc.get("job_id"),
        created_at=_iso(doc.get("created_at")),
    )


def title_from_text(text: str) -> str:
    """Название чата из первого сообщения: одна строка, обрезка по границе слова."""
    line = " ".join(text.split())
    if len(line) <= TITLE_FROM_MESSAGE:
        return line or DEFAULT_TITLE
    cut = line[:TITLE_FROM_MESSAGE].rsplit(" ", 1)[0] or line[:TITLE_FROM_MESSAGE]
    return cut.rstrip(",.;:—- ") + "…"


def clean_blocks(blocks: list[dict]) -> list[dict]:
    """Блоки через Pydantic: неизвестный тип — ошибка, точки и строки обрезаны до лимитов."""
    return [b.model_dump(mode="json") for b in _BLOCKS.validate_python(blocks)]


# ---------------------------------------------------------------------------
# Чаты
# ---------------------------------------------------------------------------


async def count_chats(db: AsyncIOMotorDatabase) -> int:
    return await db[CHATS].count_documents({})


async def list_chats(
    db: AsyncIOMotorDatabase, q: str = "", archived: bool = False, skip: int = 0, limit: int = 100
) -> list[ChatOut]:
    query: dict[str, Any] = {"archived": {"$ne": True}} if not archived else {"archived": True}
    if q.strip():
        query["title"] = {"$regex": re.escape(q.strip()), "$options": "i"}
    docs = await db[CHATS].find(query).sort([("updated_at", -1), ("_id", -1)]).skip(skip).limit(limit).to_list(limit)
    return [chat_out(d) for d in docs]


async def create_chat(db: AsyncIOMotorDatabase, title: Optional[str] = None) -> ChatOut:
    now = _now()
    doc = {
        "title": (title or "").strip() or DEFAULT_TITLE,
        "created_at": now,
        "updated_at": now,
        "archived": False,
        "summary": "",
        "summary_upto": 0,
    }
    result = await db[CHATS].insert_one(doc)
    return chat_out({**doc, "_id": result.inserted_id})


async def get_chat(db: AsyncIOMotorDatabase, chat_id: str) -> Optional[ChatOut]:
    oid = _oid(chat_id)
    doc = await db[CHATS].find_one({"_id": oid}) if oid else None
    return chat_out(doc) if doc else None


async def update_chat(db: AsyncIOMotorDatabase, chat_id: str, changes: dict[str, Any]) -> Optional[ChatOut]:
    oid = _oid(chat_id)
    if oid is None:
        return None
    doc = await db[CHATS].find_one_and_update(
        {"_id": oid}, {"$set": {**changes, "updated_at": _now()}}, return_document=ReturnDocument.AFTER
    )
    return chat_out(doc) if doc else None


async def set_summary(db: AsyncIOMotorDatabase, chat_id: str, summary: str, upto: int) -> None:
    # updated_at не трогаем: сводка — служебная, порядок списка чатов не меняется
    await db[CHATS].update_one({"_id": ObjectId(chat_id)}, {"$set": {"summary": summary, "summary_upto": upto}})


async def delete_chat(db: AsyncIOMotorDatabase, chat_id: str) -> bool:
    oid = _oid(chat_id)
    if oid is None:
        return False
    result = await db[CHATS].delete_one({"_id": oid})
    if result.deleted_count:
        await db[MESSAGES].delete_many({"chat_id": chat_id})
    return result.deleted_count == 1


# ---------------------------------------------------------------------------
# Сообщения
# ---------------------------------------------------------------------------


async def count_messages(db: AsyncIOMotorDatabase, chat_id: str) -> int:
    return await db[MESSAGES].count_documents({"chat_id": chat_id})


async def add_message(
    db: AsyncIOMotorDatabase,
    chat_id: str,
    role: str,
    content: str,
    blocks: Optional[list[dict]] = None,
    job_id: Optional[str] = None,
) -> MessageOut:
    now = _now()
    doc = {
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "blocks": clean_blocks(blocks or []),
        "job_id": job_id,
        "created_at": now,
    }
    result = await db[MESSAGES].insert_one(doc)
    await db[CHATS].update_one({"_id": ObjectId(chat_id)}, {"$set": {"updated_at": now}})
    return message_out({**doc, "_id": result.inserted_id})


async def get_message(db: AsyncIOMotorDatabase, chat_id: str, message_id: str) -> Optional[MessageOut]:
    oid = _oid(message_id)
    doc = await db[MESSAGES].find_one({"_id": oid, "chat_id": chat_id}) if oid else None
    return message_out(doc) if doc else None


async def delete_message(db: AsyncIOMotorDatabase, message_id: str) -> None:
    oid = _oid(message_id)
    if oid:
        await db[MESSAGES].delete_one({"_id": oid})


async def list_messages(
    db: AsyncIOMotorDatabase, chat_id: str, limit: int = 50, before: Optional[str] = None
) -> tuple[list[MessageOut], bool]:
    """Страница истории: последние limit сообщений (или limit перед курсором) в хронологическом порядке."""
    query: dict[str, Any] = {"chat_id": chat_id}
    before_oid = _oid(before) if before else None
    if before_oid is not None:
        query["_id"] = {"$lt": before_oid}
    docs = await db[MESSAGES].find(query).sort("_id", -1).limit(limit + 1).to_list(limit + 1)
    has_more = len(docs) > limit
    return [message_out(d) for d in reversed(docs[:limit])], has_more


async def all_messages(db: AsyncIOMotorDatabase, chat_id: str, upto_id: Optional[str] = None) -> list[MessageOut]:
    """Вся история чата по порядку (для контекста модели); upto_id — включительно."""
    query: dict[str, Any] = {"chat_id": chat_id}
    oid = _oid(upto_id) if upto_id else None
    if oid is not None:
        query["_id"] = {"$lte": oid}
    docs = await db[MESSAGES].find(query).sort("_id", 1).to_list(None)
    return [message_out(d) for d in docs]


async def mark_preview_applied(db: AsyncIOMotorDatabase, job_id: str, outcome: dict) -> None:
    """Блок capture_preview сообщения этой задачи — «применено» (после перезагрузки страницы тоже видно)."""
    doc = await db[MESSAGES].find_one({"job_id": job_id})
    if not doc:
        return
    blocks = [
        {**b, "applied": outcome} if b.get("type") == "capture_preview" and b.get("job_id") == job_id else b
        for b in doc.get("blocks") or []
    ]
    await db[MESSAGES].update_one({"_id": doc["_id"]}, {"$set": {"blocks": blocks}})
