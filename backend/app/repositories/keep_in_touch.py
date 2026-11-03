"""
Keep in touch: выборка контактов с частотой и отложенные напоминания.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..services.keep_in_touch import KeepInTouchBuckets, bucketize
from . import contacts as contacts_repo
from . import interactions as interactions_repo

_PROJECTION = {
    "first_name": 1,
    "last_name": 1,
    "company": 1,
    "tags": 1,
    "importance": 1,
    "keep_in_touch": 1,
    "last_interaction_at": 1,
    "created_at": 1,
}


async def load_buckets(db: AsyncIOMotorDatabase, today: date) -> KeepInTouchBuckets:
    docs = await db[contacts_repo.COLLECTION].find(
        {"keep_in_touch.frequency_days": {"$gt": 0}}, _PROJECTION
    ).to_list(length=None)
    # Свежие данные: события календаря могли появиться после последнего пересчёта
    last = await interactions_repo.latest_map(db, [str(d["_id"]) for d in docs])
    return bucketize(docs, last, today)


async def set_snooze(db: AsyncIOMotorDatabase, contact_id: str, until: Optional[date]) -> bool:
    """Отложить напоминание до даты (None — снять). updated_at не трогаем: наружу это не синхронизируется."""
    try:
        oid = ObjectId(contact_id)
    except (InvalidId, TypeError):
        return False
    result = await db[contacts_repo.COLLECTION].update_one(
        {"_id": oid}, {"$set": {"keep_in_touch.snoozed_until": until.isoformat() if until else None}}
    )
    return result.matched_count == 1
