"""
Роутер взаимодействий (Timeline): /api/interactions — лента с фильтрами и курсорной пагинацией,
создание, правка, удаление. Каждое изменение пересчитывает last_interaction_at у затронутых людей.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.interaction import (
    InteractionCreate,
    InteractionKind,
    InteractionOut,
    InteractionPage,
    InteractionUpdate,
)
from ..models.user import User
from ..repositories import events as events_repo
from ..repositories import interactions as repo

router = APIRouter(prefix="/api/interactions", tags=["interactions"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

EVENT_PREFIX = "event:"


def _not_found(interaction_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Взаимодействие {interaction_id!r} не найдено")


def _reject_event(interaction_id: str) -> None:
    if interaction_id.startswith(EVENT_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Встреча из календаря меняется в календаре",
        )


async def _check_contacts(db: AsyncIOMotorDatabase, contact_ids: list[str]) -> None:
    present = set(await events_repo.existing_contact_ids(db, contact_ids))
    missing = [c for c in contact_ids if c not in present]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Контакты не найдены: {', '.join(missing)}",
        )


@router.get("", response_model=InteractionPage, summary="Лента взаимодействий (новые сверху)")
async def list_interactions(
    db: DbDep,
    _user: AuthDep,
    contact_id: Optional[list[str]] = Query(default=None, description="Только с этими людьми (можно повторять)"),
    kind: Optional[list[InteractionKind]] = Query(default=None, description="Типы (можно повторять)"),
    from_: Optional[datetime] = Query(default=None, alias="from", description="Не раньше"),
    to: Optional[datetime] = Query(default=None, description="Не позже"),
    q: Optional[str] = Query(default=None, description="Поиск по заголовку и тексту"),
    cursor: Optional[str] = Query(default=None, description="next_cursor предыдущей страницы"),
    limit: int = Query(default=repo.DEFAULT_LIMIT, ge=1, le=repo.MAX_LIMIT),
    include_events: bool = Query(default=False, description="Подмешать прошедшие события календаря как встречи"),
) -> InteractionPage:
    try:
        return await repo.list_page(
            db,
            contact_ids=contact_id,
            kinds=kind,
            from_=from_,
            to=to,
            q=q,
            cursor=cursor,
            limit=limit,
            include_events=include_events,
        )
    except repo.InvalidCursor as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None


@router.post("", response_model=InteractionOut, status_code=status.HTTP_201_CREATED, summary="Добавить взаимодействие")
async def create_interaction(data: InteractionCreate, db: DbDep, _user: AuthDep) -> InteractionOut:
    await _check_contacts(db, data.contact_ids)
    return await repo.create_interaction(db, data)


@router.patch("/{interaction_id}", response_model=InteractionOut, summary="Изменить взаимодействие")
async def update_interaction(
    interaction_id: str, data: InteractionUpdate, db: DbDep, _user: AuthDep
) -> InteractionOut:
    _reject_event(interaction_id)
    if data.contact_ids is not None:
        await _check_contacts(db, data.contact_ids)
    updated = await repo.update_interaction(db, interaction_id, data)
    if updated is None:
        raise _not_found(interaction_id)
    return updated


@router.delete(
    "/{interaction_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Удалить взаимодействие"
)
async def delete_interaction(interaction_id: str, db: DbDep, _user: AuthDep) -> None:
    _reject_event(interaction_id)
    if not await repo.delete_interaction(db, interaction_id):
        raise _not_found(interaction_id)
