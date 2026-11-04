"""
Места для экрана «Места» (/contacts/locations): /api/places.

Место — это адрес контакта (или метка координат, или город, если адреса нет). Список собирается из контактов
и из коллекции places (места, добавленные вручную и пока без людей). Геокодирование не делаем — только текст.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field, field_validator

from ..auth import get_current_user, get_user_db
from ..models.contact import Location
from ..models.user import User
from ..repositories import contacts as contacts_repo

router = APIRouter(prefix="/api/places", tags=["places"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

COLLECTION = "places"


class PlaceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    city: str = Field(default="", max_length=100)

    @field_validator("name", "city", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class PlaceContact(BaseModel):
    id: str
    name: str


class PlaceOut(BaseModel):
    key: str
    name: str
    city: str = ""
    # address — название хранится в contact.address; city — место задано только городом контакта
    kind: Literal["address", "city"] = "address"
    count: int = 0
    location: Optional[Location] = None
    contacts: list[PlaceContact] = Field(default_factory=list)


def _key(name: str, city: str) -> str:
    return f"{name.casefold()}|{city.casefold()}"


def _place_of(doc: dict) -> Optional[tuple[str, str, str]]:
    """(название, город, kind) места контакта или None, если места нет."""
    address = (doc.get("address") or "").strip()
    city = (doc.get("city") or "").strip()
    label = ((doc.get("location") or {}).get("label") or "").strip()
    if address:
        return address, city, "address"
    if label:
        return label, city, "address"
    if city:
        return city, "", "city"
    return None


async def build_places(db: AsyncIOMotorDatabase) -> list[PlaceOut]:
    places: dict[str, PlaceOut] = {}
    async for doc in db[COLLECTION].find({}):
        name, city = doc.get("name", ""), doc.get("city", "")
        places[_key(name, city)] = PlaceOut(key=_key(name, city), name=name, city=city)

    projection = {"first_name": 1, "last_name": 1, "address": 1, "city": 1, "location": 1}
    query = {"$or": [{"address": {"$nin": ["", None]}}, {"city": {"$nin": ["", None]}}, {"location": {"$ne": None}}]}
    async for doc in db[contacts_repo.COLLECTION].find(query, projection):
        found = _place_of(doc)
        if found is None:
            continue
        name, city, kind = found
        place = places.setdefault(_key(name, city), PlaceOut(key=_key(name, city), name=name, city=city, kind=kind))
        full_name = f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip() or "Без имени"
        place.contacts.append(PlaceContact(id=str(doc["_id"]), name=full_name))
        place.count += 1
        if place.location is None and doc.get("location"):
            place.location = Location(**doc["location"])
    return sorted(places.values(), key=lambda p: (p.name.casefold(), p.city.casefold()))


@router.get("", response_model=list[PlaceOut], summary="Места с людьми")
async def list_places(db: DbDep, _user: AuthDep) -> list[PlaceOut]:
    return await build_places(db)


@router.post("", response_model=PlaceOut, status_code=status.HTTP_201_CREATED, summary="Добавить место")
async def create_place(data: PlaceIn, db: DbDep, _user: AuthDep) -> PlaceOut:
    if any(p.key == _key(data.name, data.city) and p.count == 0 for p in await build_places(db)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Такое место уже есть")
    if await db[COLLECTION].find_one({"name": data.name, "city": data.city}) is None:
        await db[COLLECTION].insert_one({**data.model_dump(), "created_at": datetime.now(timezone.utc)})
    for place in await build_places(db):
        if place.key == _key(data.name, data.city):
            return place
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Не удалось сохранить место")
