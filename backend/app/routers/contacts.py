"""
Роутер контактов: /api/contacts — CRUD + поиск/фильтрация.
Все маршруты защищены JWT-аутентификацией (get_current_user).
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user
from ..db import get_db
from ..models.contact import ContactCreate, ContactOut, ContactUpdate
from ..repositories import contacts as repo

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

# Алиас для аннотации зависимости БД
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
# Алиас для зависимости auth (просто проверяет токен)
AuthDep = Annotated[str, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.post(
    "/",
    response_model=ContactOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать контакт",
)
async def create_contact(
    data: ContactCreate,
    db: DbDep,
    _user: AuthDep,
) -> ContactOut:
    """Создать новый контакт. Требует авторизации."""
    return await repo.create_contact(db, data)


@router.get(
    "/",
    response_model=list[ContactOut],
    summary="Список контактов",
)
async def list_contacts(
    db: DbDep,
    _user: AuthDep,
    q: Optional[str] = Query(default=None, description="Поиск по имени/компании/email/телефону"),
    category: Optional[str] = Query(default=None, description="Фильтр по категории"),
    priority: Optional[str] = Query(default=None, description="Фильтр по приоритету"),
    skip: int = Query(default=0, ge=0, description="Пропустить N записей"),
    limit: int = Query(default=50, ge=1, le=200, description="Макс. записей в ответе"),
) -> list[ContactOut]:
    """Вернуть список контактов с опциональным поиском и фильтрацией."""
    return await repo.list_contacts(
        db, q=q, category=category, priority=priority, skip=skip, limit=limit
    )


@router.get(
    "/{contact_id}",
    response_model=ContactOut,
    summary="Получить контакт по ID",
)
async def get_contact(
    contact_id: str,
    db: DbDep,
    _user: AuthDep,
) -> ContactOut:
    """Вернуть один контакт по его ID."""
    contact = await repo.get_contact_by_id(db, contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Контакт {contact_id!r} не найден",
        )
    return contact


@router.patch(
    "/{contact_id}",
    response_model=ContactOut,
    summary="Обновить контакт (частично)",
)
async def update_contact(
    contact_id: str,
    data: ContactUpdate,
    db: DbDep,
    _user: AuthDep,
) -> ContactOut:
    """PATCH — обновить только переданные поля контакта."""
    contact = await repo.update_contact(db, contact_id, data)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Контакт {contact_id!r} не найден",
        )
    return contact


@router.delete(
    "/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Удалить контакт",
)
async def delete_contact(
    contact_id: str,
    db: DbDep,
    _user: AuthDep,
) -> None:
    """Удалить контакт по ID. Возвращает 204 No Content при успехе."""
    deleted = await repo.delete_contact(db, contact_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Контакт {contact_id!r} не найден",
        )
