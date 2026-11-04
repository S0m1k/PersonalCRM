"""
Дубли контактов: поиск пар-кандидатов, «не дубль» (dedup_dismissed) и слияние.

Оценку пары даёт sync/dedup.find_duplicates; здесь — перебор по «корзинам» (телефон, email, начало
слова в имени), чтобы не сравнивать все пары, и слияние всех полей контакта, а не только телефонов.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.contact import normalize_labels
from ..repositories import attachments as attachments_repo
from ..repositories import contacts as contacts_repo
from ..repositories import events as events_repo
from ..repositories import interactions as interactions_repo
from ..repositories import questions as questions_repo
from ..sync.dedup import find_duplicates, merge_contacts, normalize_phone

DISMISSED = "dedup_dismissed"
MAX_CONTACTS = 5000  # потолок просмотра; дальше — слияние по частям
MAX_BUCKET = 200  # слишком «общая» корзина (тысяча Александров) пар не порождает
MIN_TOKEN = 3
TOKEN_PREFIX = 4
MAX_PAIRS = 200

_SCALAR_FILL = ("description", "first_met_note", "address", "priority", "category", "first_met_at")
_NONE_FILL = ("importance", "closeness", "location")


def pair_key(a_id: str, b_id: str) -> str:
    first, second = sorted((a_id, b_id))
    return f"{first}|{second}"


# ---------------------------------------------------------------------------
# Поиск пар
# ---------------------------------------------------------------------------


def _name_tokens(doc: dict) -> list[str]:
    return sorted(f"{doc.get('first_name', '')} {doc.get('last_name', '')}".lower().split())


def _for_scoring(doc: dict) -> dict:
    """Копия для оценки: имя из отсортированных слов, чтобы «Иван Иванов» и «Иванов Иван» совпали."""
    return {**doc, "first_name": " ".join(_name_tokens(doc)), "last_name": ""}


def _bucket_keys(doc: dict) -> set[str]:
    keys = {f"p:{normalize_phone(p['value'])}" for p in doc.get("phones") or [] if p.get("value")}
    keys |= {f"e:{e['value'].strip().lower()}" for e in doc.get("emails") or [] if e.get("value")}
    keys |= {f"n:{t[:TOKEN_PREFIX]}" for t in _name_tokens(doc) if len(t) >= MIN_TOKEN}
    keys.discard("p:")
    return keys


def candidate_pairs(docs: list[dict]) -> list[dict]:
    """Пары с оценкой ≥70 (по убыванию), каждая один раз: {a, b, score, reasons} (a, b — документы)."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, doc in enumerate(docs):
        for key in _bucket_keys(doc):
            buckets[key].append(index)

    seen: set[tuple[int, int]] = set()
    found: list[dict] = []
    for members in buckets.values():
        if len(members) < 2 or len(members) > MAX_BUCKET:
            continue
        for i, j in combinations(sorted(members), 2):
            if (i, j) in seen:
                continue
            seen.add((i, j))
            match = find_duplicates(_for_scoring(docs[i]), [_for_scoring(docs[j])])
            if match:
                found.append({"a": docs[i], "b": docs[j], "score": match[0]["score"], "reasons": match[0]["reasons"]})
    return sorted(found, key=lambda p: -p["score"])


async def dismissed_keys(db: AsyncIOMotorDatabase) -> set[str]:
    return {d["key"] async for d in db[DISMISSED].find({}, {"key": 1})}


async def suggest(db: AsyncIOMotorDatabase) -> list[dict]:
    """Предложения дублей без отклонённых пар."""
    docs = await db[contacts_repo.COLLECTION].find({}).limit(MAX_CONTACTS).to_list(length=MAX_CONTACTS)
    for doc in docs:
        doc["_sid"] = str(doc["_id"])
    hidden = await dismissed_keys(db)
    pairs = [p for p in candidate_pairs(docs) if pair_key(p["a"]["_sid"], p["b"]["_sid"]) not in hidden]
    return pairs[:MAX_PAIRS]


async def dismiss(db: AsyncIOMotorDatabase, a_id: str, b_id: str) -> None:
    await db[DISMISSED].update_one(
        {"key": pair_key(a_id, b_id)},
        {"$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def _forget_dismissals(db: AsyncIOMotorDatabase, contact_ids: list[str]) -> None:
    for cid in contact_ids:
        await db[DISMISSED].delete_many({"key": {"$regex": f"(^|\\|){cid}(\\||$)"}})


# ---------------------------------------------------------------------------
# Слияние
# ---------------------------------------------------------------------------


def _union(first: list, second: list) -> list:
    return list(dict.fromkeys([*first, *second]))


def merge_documents(keep: dict, other: dict) -> dict:
    """
    Поля для $set у оставляемого контакта: его данные главные, из `other` дописывается недостающее.
    Телефоны, email и базовые поля — через sync/dedup.merge_contacts, остальное (Sprint 11) — здесь.
    """
    merged = merge_contacts(keep, other)
    changes: dict[str, Any] = {
        key: merged[key] for key in ("phones", "emails", "company", "position", "city", "birthday", "external_ids", "sources")
    }
    if keep.get("notes") and other.get("notes") and keep["notes"] != other["notes"]:
        changes["notes"] = f"{keep['notes']}\n\n{other['notes']}"
    else:
        changes["notes"] = merged.get("notes", "")

    for name in _SCALAR_FILL:
        value = keep.get(name) or other.get(name)
        if value:
            changes[name] = value
    for name in _NONE_FILL:
        changes[name] = keep.get(name) if keep.get(name) is not None else other.get(name)

    changes["tags"] = normalize_labels(_union(keep.get("tags") or [], other.get("tags") or []))
    changes["life_areas"] = normalize_labels(_union(keep.get("life_areas") or [], other.get("life_areas") or []))
    changes["group_ids"] = _union(keep.get("group_ids") or [], other.get("group_ids") or [])

    kit = dict(keep.get("keep_in_touch") or {})
    if kit.get("frequency_days") is None:
        kit["frequency_days"] = (other.get("keep_in_touch") or {}).get("frequency_days")
    kit.setdefault("snoozed_until", None)
    changes["keep_in_touch"] = kit

    social = dict(keep.get("social") or {})
    for key, value in (other.get("social") or {}).items():
        if not social.get(key) and value:
            social[key] = value
    changes["social"] = social

    own_keys = {f["key"] for f in keep.get("custom_fields") or []}
    changes["custom_fields"] = [
        *(keep.get("custom_fields") or []),
        *(f for f in other.get("custom_fields") or [] if f.get("key") not in own_keys),
    ]
    related = {r["contact_id"] for r in keep.get("relationships") or []}
    changes["relationships"] = [
        *(keep.get("relationships") or []),
        *(r for r in other.get("relationships") or [] if r.get("contact_id") not in related),
    ]

    if not keep.get("template_id") and other.get("template_id"):
        changes["template_id"] = other["template_id"]
    if changes.get("template_id", keep.get("template_id")) == other.get("template_id"):
        changes["fields"] = {**(other.get("fields") or {}), **(keep.get("fields") or {})}
    return changes


async def _relink(db: AsyncIOMotorDatabase, keep_id: str, old_id: str) -> None:
    """Всё, что ссылалось на old_id, теперь ссылается на keep_id."""
    for collection, fields in (
        (interactions_repo.COLLECTION, ("contact_ids",)),
        (events_repo.COLLECTION, ("contact_ids", "manual_contact_ids", "excluded_contact_ids")),
    ):
        for field in fields:
            await db[collection].update_many({field: old_id}, {"$addToSet": {field: keep_id}})
            await db[collection].update_many({field: old_id}, {"$pull": {field: old_id}})
    await db[questions_repo.COLLECTION].update_many({"contact_id": old_id}, {"$set": {"contact_id": keep_id}})
    await db[attachments_repo.COLLECTION].update_many({"contact_id": old_id}, {"$set": {"contact_id": keep_id}})

    # Связи других контактов: переадресовать, без дублей и без связи с самим собой
    cursor = db[contacts_repo.COLLECTION].find({"relationships.contact_id": old_id}, {"relationships": 1})
    async for doc in cursor:
        rels: list[dict] = []
        for rel in doc.get("relationships") or []:
            target = keep_id if rel.get("contact_id") == old_id else rel.get("contact_id")
            if str(doc["_id"]) == target or any(r["contact_id"] == target for r in rels):
                continue
            rels.append({**rel, "contact_id": target})
        await db[contacts_repo.COLLECTION].update_one({"_id": doc["_id"]}, {"$set": {"relationships": rels}})


async def merge(db: AsyncIOMotorDatabase, keep_id: str, merge_ids: list[str]) -> Optional[dict]:
    """
    Влить merge_ids в keep_id и удалить их. None — если какого-то из контактов нет
    (тогда ничего не меняется). Возвращает документ оставленного контакта.
    """
    oid = contacts_repo._parse_oid  # noqa: SLF001 — тот же разбор id, что в репозитории
    keep_oid = oid(keep_id)
    other_oids = [oid(m) for m in merge_ids]
    if keep_oid is None or any(o is None for o in other_oids):
        return None
    coll = db[contacts_repo.COLLECTION]
    keep = await coll.find_one({"_id": keep_oid})
    others = [await coll.find_one({"_id": o}) for o in other_oids]
    if keep is None or any(o is None for o in others):
        return None

    current = keep
    for other in others:
        changes = merge_documents(current, other)
        current = {**current, **changes}
    current["updated_at"] = datetime.now(timezone.utc)
    update = {k: v for k, v in current.items() if k not in ("_id", "created_at", "last_interaction_at", "_sid")}
    await coll.update_one({"_id": keep_oid}, {"$set": update})

    for merge_id in merge_ids:
        await _relink(db, keep_id, merge_id)
        await coll.delete_one({"_id": oid(merge_id)})
    await _forget_dismissals(db, merge_ids)
    await interactions_repo.recompute_last_interaction(db, [keep_id])
    return await coll.find_one({"_id": keep_oid})
