"""
Роутер геокодирования: /api/geo/search — поиск места для карты,
/api/geo/geocode-contacts — фоновое заполнение location у контактов с адресом / городом.
"""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from ..auth import get_current_user, get_user_db
from ..config import settings
from ..db import get_db
from ..models.user import User
from ..services import geocode

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/geo", tags=["geo"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
SystemDbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

# Пользователи, у которых поиск координат уже идёт: повторный запуск не плодит параллельные циклы
_running: set[str] = set()


class PlaceOut(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    label: str


class GeocodeStarted(BaseModel):
    queued: int
    already_running: bool = False


def _require_enabled() -> None:
    if not settings.geocoding_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Геокодирование отключено")


@router.get("/search", response_model=list[PlaceOut], summary="Поиск места (Nominatim, с кэшем)")
async def search(
    system_db: SystemDbDep,
    _user: AuthDep,
    q: str = Query(..., min_length=2, max_length=geocode.QUERY_MAX_LEN),
    limit: int = Query(default=5, ge=1, le=geocode.MAX_PLACES),
) -> list[PlaceOut]:
    _require_enabled()
    try:
        places = await geocode.search_places(system_db, q, limit=limit)
    except httpx.HTTPError as exc:
        logger.warning("Nominatim недоступен: %s", exc.__class__.__name__)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Сервис поиска мест недоступен") from exc
    return [PlaceOut(**p.as_dict()) for p in places]


async def _run(user_id: str, system_db: AsyncIOMotorDatabase, db: AsyncIOMotorDatabase) -> None:
    try:
        counts = await geocode.geocode_contacts(system_db, db)
        logger.info("Геокодирование контактов: %s", counts)
    except Exception:  # noqa: BLE001 — фоновая задача, ошибка не должна пропасть молча
        logger.exception("Геокодирование контактов упало")
    finally:
        _running.discard(user_id)


@router.post(
    "/geocode-contacts",
    response_model=GeocodeStarted,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Найти координаты контактов с адресом/городом (в фоне)",
)
async def geocode_contacts(
    background: BackgroundTasks, db: DbDep, system_db: SystemDbDep, user: AuthDep
) -> GeocodeStarted:
    _require_enabled()
    queued = min(await geocode.count_missing(db), geocode.BULK_LIMIT)
    if user.id in _running:
        return GeocodeStarted(queued=queued, already_running=True)
    if queued:
        _running.add(user.id)
        background.add_task(_run, user.id, system_db, db)
    return GeocodeStarted(queued=queued)


@router.get("/missing", summary="Сколько контактов можно геокодировать")
async def missing(db: DbDep, _user: AuthDep) -> dict[str, int]:
    return {"missing": await geocode.count_missing(db)}
