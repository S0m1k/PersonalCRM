"""
Адресная книга CardDAV поверх коллекции contacts.

Карточка = контакт. Имя файла (href) — то, что выбрал телефон при создании (`dav_name`),
иначе `<id>.vcf`. UID телефона хранится в `dav_uid`, чтобы карточка вернулась с тем же UID.
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

from ..models.contact import ContactCreate, ContactOut
from ..repositories import contacts as contacts_repo
from ..repositories import questions as questions_repo
from ..services.vcard import contact_to_vcard, vcard_to_fields, vcard_uid

CONTACTS = "contacts"
TRASH = "contacts_trash"
SOURCE = "phone"

# Имя карточки от клиента: без слэшей и прочего, что может увести за пределы книги
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._@%+=~-]{1,200}\.vcf$")


@dataclass(frozen=True)
class Card:
    name: str
    etag: str
    doc: dict


def is_valid_name(name: str) -> bool:
    return bool(_SAFE_NAME.match(name))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _etag(doc: dict) -> str:
    stamp = f"{doc['_id']}:{_utc(doc['updated_at']).isoformat()}"
    return '"' + hashlib.sha1(stamp.encode()).hexdigest()[:20] + '"'


def _card(doc: dict) -> Card:
    return Card(name=doc.get("dav_name") or f"{doc['_id']}.vcf", etag=_etag(doc), doc=doc)


def render(card: Card) -> str:
    return contact_to_vcard(ContactOut.from_mongo(card.doc), uid=card.doc.get("dav_uid"))


async def list_cards(db: AsyncIOMotorDatabase, with_data: bool = False) -> list[Card]:
    projection = None if with_data else {"_id": 1, "updated_at": 1, "dav_name": 1}
    docs = await db[CONTACTS].find({}, projection).to_list(length=None)
    return [_card(d) for d in docs]


async def ctag(db: AsyncIOMotorDatabase) -> str:
    """Меняется при любом изменении книги: правка, создание, удаление контакта."""
    cards = await list_cards(db)
    digest = hashlib.sha1("|".join(sorted(f"{c.name}{c.etag}" for c in cards)).encode())
    return f'"{len(cards)}-{digest.hexdigest()[:16]}"'


async def find(db: AsyncIOMotorDatabase, name: str) -> Optional[Card]:
    doc = await db[CONTACTS].find_one({"dav_name": name})
    if doc is None and name.endswith(".vcf"):
        try:
            doc = await db[CONTACTS].find_one({"_id": ObjectId(name[: -len(".vcf")])})
        except (InvalidId, TypeError):
            doc = None
    return _card(doc) if doc else None


async def create(db: AsyncIOMotorDatabase, name: str, text: str) -> Card:
    fields = vcard_to_fields(text)
    contact = await contacts_repo.create_contact(db, ContactCreate(**fields, source=SOURCE))
    await db[CONTACTS].update_one(
        {"_id": ObjectId(contact.id)}, {"$set": {"dav_name": name, "dav_uid": vcard_uid(text)}}
    )
    return await find(db, name)  # type: ignore[return-value]


async def update(db: AsyncIOMotorDatabase, card: Card, text: str) -> Card:
    """Обновить только то, что есть в vCard; шаблон, свои поля, приоритет и вопросы не трогаем."""
    fields = vcard_to_fields(text)
    # Проверка через модель: тот же формат дня рождения и т.п., что и в API
    checked = ContactCreate(**fields).model_dump(include=set(fields))
    changes = {**checked, "updated_at": datetime.now(timezone.utc)}
    uid = vcard_uid(text)
    if uid:
        changes["dav_uid"] = uid
    await db[CONTACTS].update_one({"_id": card.doc["_id"]}, {"$set": changes})
    return await find(db, card.name)  # type: ignore[return-value]


async def delete(db: AsyncIOMotorDatabase, card: Card) -> None:
    """
    Удаление с телефона — в корзину (contacts_trash), чтобы случайное удаление можно было вернуть.
    Вложения (коллекция attachments и файлы в S3) не трогаем: они привязаны к contact_id и вернутся
    вместе с контактом, если восстановить его с тем же _id. До этого они занимают квоту пользователя.
    """
    contact_id = str(card.doc["_id"])
    full = await db[CONTACTS].find_one({"_id": card.doc["_id"]})
    if full is None:
        return
    trashed = {k: v for k, v in full.items() if k != "_id"}
    await db[TRASH].insert_one(
        {**trashed, "contact_id": contact_id, "deleted_at": datetime.now(timezone.utc), "deleted_via": "carddav"}
    )
    await contacts_repo.delete_contact(db, contact_id)
    await questions_repo.delete_for_contact(db, contact_id)
