"""
Роутер сохранённых видов списка контактов: /api/views — CRUD.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.user import User
from ..models.view import ViewCreate, ViewOut, ViewUpdate
from ..repositories import views as repo

router = APIRouter(prefix="/api/views", tags=["views"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _not_found(view_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Вид {view_id!r} не найден")


def _duplicate() -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Вид с таким названием уже есть")


@router.get("", response_model=list[ViewOut], summary="Сохранённые виды")
async def list_views(db: DbDep, _user: AuthDep) -> list[ViewOut]:
    return await repo.list_views(db)


@router.post("", response_model=ViewOut, status_code=status.HTTP_201_CREATED, summary="Сохранить вид")
async def create_view(data: ViewCreate, db: DbDep, _user: AuthDep) -> ViewOut:
    if await repo.name_taken(db, data.name):
        raise _duplicate()
    return await repo.create_view(db, data)


@router.get("/{view_id}", response_model=ViewOut, summary="Вид по id")
async def get_view(view_id: str, db: DbDep, _user: AuthDep) -> ViewOut:
    view = await repo.get_view(db, view_id)
    if view is None:
        raise _not_found(view_id)
    return view


@router.patch("/{view_id}", response_model=ViewOut, summary="Изменить вид")
async def update_view(view_id: str, data: ViewUpdate, db: DbDep, _user: AuthDep) -> ViewOut:
    if data.name is not None and await repo.name_taken(db, data.name, exclude_id=view_id):
        raise _duplicate()
    view = await repo.update_view(db, view_id, data)
    if view is None:
        raise _not_found(view_id)
    return view


@router.delete("/{view_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Удалить вид")
async def delete_view(view_id: str, db: DbDep, _user: AuthDep) -> None:
    if not await repo.delete_view(db, view_id):
        raise _not_found(view_id)
