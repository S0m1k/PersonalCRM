"""
Геокодирование через Nominatim (OpenStreetMap).

Политика использования Nominatim: не чаще 1 запроса в секунду с одного клиента и
осмысленный User-Agent. Поэтому:
  * все запросы наружу идут через общий throttle (1 запрос / сек на процесс);
  * ответы кэшируются в общей коллекции geocode_cache (ключ — нормализованная строка места);
    в кэше нет ничего, кроме текста места и найденных координат;
  * в User-Agent нет e-mail и вообще персональных данных.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "PersonalCRM self-hosted"
CACHE_COLLECTION = "geocode_cache"
REQUEST_TIMEOUT_S = 10.0
QUERY_MAX_LEN = 300
MAX_PLACES = 5  # всегда просим и кэшируем 5 вариантов; вызывающий берёт сколько нужно
# Контактов, обрабатываемых одним запуском «найти координаты» (≈ 2 минуты при 1 запросе/сек)
BULK_LIMIT = 100

# Нижняя граница между запросами к Nominatim. Тесты подменяют на 0.
min_interval_s = 1.0
_throttle_lock: Optional[asyncio.Lock] = None
_last_request_at = 0.0


@dataclass(frozen=True)
class Place:
    lat: float
    lng: float
    label: str

    def as_dict(self) -> dict:
        return {"lat": self.lat, "lng": self.lng, "label": self.label}


def normalize_query(query: str) -> str:
    """Ключ кэша: нижний регистр, схлопнутые пробелы, ограниченная длина."""
    return " ".join(query.lower().split())[:QUERY_MAX_LEN]


def _lock() -> asyncio.Lock:
    global _throttle_lock
    if _throttle_lock is None:
        _throttle_lock = asyncio.Lock()
    return _throttle_lock


async def _wait_turn() -> None:
    """Держит паузу не меньше min_interval_s между запросами наружу (общую на все запросы процесса)."""
    global _last_request_at
    wait = _last_request_at + min_interval_s - time.monotonic()
    if wait > 0:
        await asyncio.sleep(wait)
    _last_request_at = time.monotonic()


def _parse(items: list[dict]) -> list[Place]:
    places: list[Place] = []
    for item in items:
        try:
            places.append(Place(lat=float(item["lat"]), lng=float(item["lon"]), label=str(item.get("display_name", ""))))
        except (KeyError, TypeError, ValueError):
            continue
    return places


async def fetch_nominatim(query: str, limit: int) -> list[dict]:
    """Единственное место, где мы ходим в сеть (подменяется в тестах)."""
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(NOMINATIM_URL, params={"q": query, "format": "jsonv2", "limit": limit})
        resp.raise_for_status()
        data = resp.json()
    return data if isinstance(data, list) else []


async def search_places(system_db: AsyncIOMotorDatabase, query: str, limit: int = MAX_PLACES) -> list[Place]:
    """
    Найти места по тексту. Сначала кэш; при промахе — один запрос к Nominatim под общим throttle.
    Ошибка сети пробрасывается (httpx.HTTPError); в кэш пишутся только успешные ответы.
    """
    key = normalize_query(query)
    if not key:
        return []
    cache = system_db[CACHE_COLLECTION]
    hit = await cache.find_one({"_id": key})
    if hit is not None:
        return [Place(**p) for p in hit["places"]][:limit]

    async with _lock():
        # Пока ждали очередь, соседний запрос мог уже положить ответ в кэш
        hit = await cache.find_one({"_id": key})
        if hit is not None:
            return [Place(**p) for p in hit["places"]][:limit]
        await _wait_turn()
        items = await fetch_nominatim(key, MAX_PLACES)
    places = _parse(items)
    await cache.replace_one({"_id": key}, {"_id": key, "places": [p.as_dict() for p in places]}, upsert=True)
    return places[:limit]


def contact_place_query(doc: dict) -> str:
    """Что искать для контакта: адрес, иначе город."""
    return (doc.get("address") or "").strip() or (doc.get("city") or "").strip()


async def geocode_contacts(system_db: AsyncIOMotorDatabase, db: AsyncIOMotorDatabase) -> dict[str, int]:
    """
    Заполнить location у контактов с address/city, но без location.
    Уже стоящие координаты (в том числе выставленные вручную) не трогаем: фильтр — location пуст,
    и запись условная — на случай, если пользователь поставил точку, пока шёл поиск.
    """
    docs = await (
        db["contacts"]
        .find({"location": None, "$or": [{"address": {"$gt": ""}}, {"city": {"$gt": ""}}]})
        .limit(BULK_LIMIT)
        .to_list(length=BULK_LIMIT)
    )
    counts = {"found": 0, "not_found": 0, "errors": 0}
    for doc in docs:
        query = contact_place_query(doc)
        if not query:
            continue
        try:
            places = await search_places(system_db, query, limit=1)
        except httpx.HTTPError as exc:
            logger.warning("Геокодирование не удалось: %s", exc.__class__.__name__)
            counts["errors"] += 1
            continue
        if not places:
            counts["not_found"] += 1
            continue
        result = await db["contacts"].update_one(
            {"_id": doc["_id"], "location": None}, {"$set": {"location": places[0].as_dict()}}
        )
        counts["found" if result.modified_count else "not_found"] += 1
    return counts


async def count_missing(db: AsyncIOMotorDatabase) -> int:
    """Сколько контактов можно геокодировать: есть address/city, нет location."""
    return await db["contacts"].count_documents(
        {"location": None, "$or": [{"address": {"$gt": ""}}, {"city": {"$gt": ""}}]}
    )
