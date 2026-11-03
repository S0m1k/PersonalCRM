"""
Роутер Keep in touch: GET /api/keep-in-touch, POST /api/contacts/{id}/snooze и /touched.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from ..auth import get_current_user, get_user_db
from ..models.contact import ContactOut
from ..models.interaction import InteractionCreate, InteractionKind, InteractionOut
from ..models.user import User
from ..repositories import contacts as contacts_repo
from ..repositories import interactions as interactions_repo
from ..repositories import keep_in_touch as repo
from ..services.keep_in_touch import KeepInTouchBuckets

router = APIRouter(tags=["keep-in-touch"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

SNOOZE_MAX_DAYS = 365
TOUCHED_TITLE = "Связались"


class SnoozeBody(BaseModel):
    days: int = Field(..., ge=1, le=SNOOZE_MAX_DAYS)
    # Локальная дата пользователя (сервер может жить в UTC); по умолчанию — дата сервера
    today: Optional[date] = None


class TouchedBody(BaseModel):
    kind: InteractionKind = "note"
    title: str = Field(default=TOUCHED_TITLE, max_length=300)
    body: str = Field(default="", max_length=20_000)


def _not_found(contact_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Контакт {contact_id!r} не найден")


@router.get("/api/keep-in-touch", response_model=KeepInTouchBuckets, summary="Кому пора написать")
async def keep_in_touch(
    db: DbDep,
    _user: AuthDep,
    today: Optional[date] = Query(default=None, description="Локальная дата пользователя"),
) -> KeepInTouchBuckets:
    return await repo.load_buckets(db, today or date.today())


@router.post("/api/contacts/{contact_id}/snooze", response_model=ContactOut, summary="Отложить напоминание")
async def snooze(contact_id: str, data: SnoozeBody, db: DbDep, _user: AuthDep) -> ContactOut:
    until = (data.today or date.today()) + timedelta(days=data.days)
    if not await repo.set_snooze(db, contact_id, until):
        raise _not_found(contact_id)
    contact = await contacts_repo.get_contact_by_id(db, contact_id)
    if contact is None:
        raise _not_found(contact_id)
    return contact


@router.post(
    "/api/contacts/{contact_id}/touched",
    response_model=InteractionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Отметить «связались»: быстрое взаимодействие, отложенное напоминание снимается",
)
async def touched(contact_id: str, db: DbDep, _user: AuthDep, data: Optional[TouchedBody] = None) -> InteractionOut:
    if await contacts_repo.get_contact_by_id(db, contact_id) is None:
        raise _not_found(contact_id)
    data = data or TouchedBody()
    created = await interactions_repo.create_interaction(
        db, InteractionCreate(contact_ids=[contact_id], kind=data.kind, title=data.title, body=data.body)
    )
    await repo.set_snooze(db, contact_id, None)
    return created
