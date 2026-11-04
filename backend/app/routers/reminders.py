"""
Роутер напоминаний: /api/reminders.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.reminder import ReminderCreate, ReminderOut, ReminderStatus, ReminderUpdate
from ..models.user import User
from ..repositories import contacts as contacts_repo
from ..repositories import reminders as repo

router = APIRouter(prefix="/api/reminders", tags=["reminders"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _not_found(reminder_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Напоминание {reminder_id!r} не найдено")


async def _ensure_contact(db: AsyncIOMotorDatabase, contact_id: Optional[str]) -> None:
    if contact_id and await contacts_repo.get_contact_by_id(db, contact_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден")


@router.get("", response_model=list[ReminderOut], summary="Список напоминаний")
async def list_reminders(
    db: DbDep,
    _user: AuthDep,
    status_: ReminderStatus = Query(default="all", alias="status"),
    date_from: Optional[str] = Query(default=None, alias="from", description="ГГГГ-ММ-ДД, включительно"),
    date_to: Optional[str] = Query(default=None, alias="to", description="ГГГГ-ММ-ДД, включительно"),
    contact_id: Optional[str] = Query(default=None),
) -> list[ReminderOut]:
    return await repo.list_reminders(db, status_, date_from, date_to, contact_id)


@router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED, summary="Добавить напоминание")
async def create_reminder(data: ReminderCreate, db: DbDep, _user: AuthDep) -> ReminderOut:
    await _ensure_contact(db, data.contact_id)
    return await repo.create_reminder(db, data)


@router.patch("/{reminder_id}", response_model=ReminderOut, summary="Изменить напоминание")
async def update_reminder(reminder_id: str, data: ReminderUpdate, db: DbDep, _user: AuthDep) -> ReminderOut:
    await _ensure_contact(db, data.contact_id)
    reminder = await repo.update_reminder(db, reminder_id, data)
    if reminder is None:
        raise _not_found(reminder_id)
    return reminder


@router.post("/{reminder_id}/done", response_model=ReminderOut, summary="Отметить выполненным")
async def done_reminder(reminder_id: str, db: DbDep, _user: AuthDep) -> ReminderOut:
    reminder = await repo.mark_done(db, reminder_id)
    if reminder is None:
        raise _not_found(reminder_id)
    return reminder


@router.delete(
    "/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Удалить напоминание"
)
async def delete_reminder(reminder_id: str, db: DbDep, _user: AuthDep) -> None:
    if not await repo.delete_reminder(db, reminder_id):
        raise _not_found(reminder_id)
