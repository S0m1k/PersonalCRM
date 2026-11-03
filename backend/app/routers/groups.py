"""
Роутер групп контактов: /api/groups — список с числом участников, создание, правка, удаление.
Удаление группы убирает её id у всех контактов.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.group import GroupCreate, GroupOut, GroupUpdate
from ..models.user import User
from ..repositories import groups as repo

router = APIRouter(prefix="/api/groups", tags=["groups"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _not_found(group_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Группа {group_id!r} не найдена")


def _duplicate() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Группа с таким названием уже есть")


@router.get("", response_model=list[GroupOut], summary="Группы с числом участников")
async def list_groups(db: DbDep, _user: AuthDep) -> list[GroupOut]:
    return await repo.list_groups(db)


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED, summary="Создать группу")
async def create_group(data: GroupCreate, db: DbDep, _user: AuthDep) -> GroupOut:
    if await repo.name_taken(db, data.name):
        raise _duplicate()
    return await repo.create_group(db, data)


@router.patch("/{group_id}", response_model=GroupOut, summary="Изменить группу")
async def update_group(group_id: str, data: GroupUpdate, db: DbDep, _user: AuthDep) -> GroupOut:
    if data.name is not None and await repo.name_taken(db, data.name, exclude_id=group_id):
        raise _duplicate()
    group = await repo.update_group(db, group_id, data)
    if group is None:
        raise _not_found(group_id)
    return group


@router.delete(
    "/{group_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Удалить группу"
)
async def delete_group(group_id: str, db: DbDep, _user: AuthDep) -> None:
    if not await repo.delete_group(db, group_id):
        raise _not_found(group_id)
