"""
Календарь CalDAV поверх коллекции events.

Событие = ресурс `<имя>.ics`. Имя — то, что выбрал телефон при создании (`dav_name`), иначе `<id>.ics`.
С телефона приходит полный iCalendar: его целиком запоминаем (`dav_ical`) и отдаём обратно, пока событие
не менялось в CRM (`dav_ical_rev` совпадает с updated_at) — так сохраняются VTIMEZONE, RRULE, напоминания.
После правки в CRM карточка собирается заново из полей, а RRULE и напоминания берутся из `dav_extra`.
События из Outlook / Google (есть connection_id и external_id) с телефона только читаются:
их запись у провайдера делает CRM (там проверка прав и повторные попытки).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.event import Attendee, EventCreate, EventOut
from ..repositories import events as events_repo
from ..services.ical import event_to_ical, ical_to_fields, ical_uid

EVENTS = "events"
TRASH = "events_trash"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._@%+=~-]{1,200}\.ics$")
_FIELDS = ("title", "start", "end", "all_day", "timezone", "location", "description")


@dataclass(frozen=True)
class Item:
    name: str
    etag: str
    doc: dict

    @property
    def is_read_only(self) -> bool:
        return is_provider_event(self.doc)


def is_valid_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name))


def is_provider_event(doc: dict) -> bool:
    return bool(doc.get("connection_id") and doc.get("external_id"))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _stamp(doc: dict) -> str:
    return _utc(doc["updated_at"]).isoformat()


def _etag(doc: dict) -> str:
    return '"' + hashlib.sha1(f"{doc['_id']}:{_stamp(doc)}".encode()).hexdigest()[:20] + '"'


def _item(doc: dict) -> Item:
    return Item(name=doc.get("dav_name") or f"{doc['_id']}.ics", etag=_etag(doc), doc=doc)


def render(item: Item) -> str:
    doc = item.doc
    if doc.get("dav_ical") and doc.get("dav_ical_rev") == _stamp(doc):
        return doc["dav_ical"]
    return event_to_ical(EventOut.from_mongo(doc), uid=doc.get("dav_uid"), extra=doc.get("dav_extra"))


async def list_items(
    db: AsyncIOMotorDatabase, start: Optional[datetime] = None, end: Optional[datetime] = None
) -> list[Item]:
    """События, пересекающиеся с [start, end); повторяющиеся — если начались до конца периода."""
    query: dict = {}
    if start is not None and end is not None:
        query["$or"] = [
            {"start": {"$lt": end}, "end": {"$gt": start}},
            {"dav_recurring": True, "start": {"$lt": end}},
        ]
    docs = await db[EVENTS].find(query).sort("start", 1).to_list(length=None)
    return [_item(d) for d in docs]


async def ctag(db: AsyncIOMotorDatabase) -> str:
    items = await list_items(db)
    digest = hashlib.sha1("|".join(sorted(f"{i.name}{i.etag}" for i in items)).encode())
    return f'"{len(items)}-{digest.hexdigest()[:16]}"'


async def find(db: AsyncIOMotorDatabase, name: str) -> Optional[Item]:
    doc = await db[EVENTS].find_one({"dav_name": name})
    if doc is None and name.endswith(".ics"):
        try:
            doc = await db[EVENTS].find_one({"_id": ObjectId(name[: -len(".ics")])})
        except (InvalidId, TypeError):
            doc = None
    return _item(doc) if doc else None


def _validated(text: str) -> dict:
    """Поля события из iCalendar, проверенные той же моделью, что и API (ValueError — для 400)."""
    parsed = ical_to_fields(text)
    attendees = [Attendee(**a) for a in parsed["attendees"]]
    checked = EventCreate(**{k: parsed[k] for k in _FIELDS}, attendees=attendees)
    fields = checked.model_dump(include=set(_FIELDS) | {"attendees"})
    fields["dav_extra"] = parsed["dav_extra"]
    fields["dav_recurring"] = any(line.upper().startswith("RRULE") for line in parsed["dav_extra"])
    return fields


async def _seal(db: AsyncIOMotorDatabase, event_id: ObjectId, text: str, **extra) -> Item:
    """Запомнить исходный iCalendar вместе с моментом, на который он соответствует событию."""
    doc = await db[EVENTS].find_one({"_id": event_id})
    await db[EVENTS].update_one(
        {"_id": event_id}, {"$set": {"dav_ical": text, "dav_ical_rev": _stamp(doc), **extra}}
    )
    return _item(await db[EVENTS].find_one({"_id": event_id}))


async def create(db: AsyncIOMotorDatabase, name: str, text: str) -> Item:
    fields = _validated(text)
    attendees = [Attendee(**a) for a in fields["attendees"]]
    auto = await events_repo.match_contacts(db, attendees)
    doc = await events_repo.insert_event(
        db, {**fields, "contact_ids": events_repo.combine_links(auto, [], []), "manual_contact_ids": []}
    )
    return await _seal(db, doc["_id"], text, dav_name=name, dav_uid=ical_uid(text))


async def update(db: AsyncIOMotorDatabase, item: Item, text: str) -> Item:
    """Обновить то, что есть в iCalendar; привязки к людям (вручную) и push_questions не трогаем."""
    doc = item.doc
    fields = _validated(text)
    attendees = [Attendee(**a) for a in fields["attendees"]]
    auto = await events_repo.match_contacts(db, attendees)
    contact_ids = events_repo.combine_links(
        auto, doc.get("manual_contact_ids") or [], doc.get("excluded_contact_ids") or []
    )
    uid = ical_uid(text)
    await events_repo.update_event_doc(
        db, str(doc["_id"]), {**fields, "contact_ids": contact_ids, **({"dav_uid": uid} if uid else {})}
    )
    return await _seal(db, doc["_id"], text)


async def delete(db: AsyncIOMotorDatabase, item: Item) -> None:
    """Удаление с телефона — в корзину (events_trash), чтобы случайное удаление можно было вернуть."""
    doc = await db[EVENTS].find_one({"_id": item.doc["_id"]})
    if doc is None:
        return
    trashed = {k: v for k, v in doc.items() if k != "_id"}
    await db[TRASH].insert_one(
        {**trashed, "event_id": str(doc["_id"]), "deleted_at": datetime.now(timezone.utc), "deleted_via": "caldav"}
    )
    await events_repo.delete_event(db, str(doc["_id"]))
