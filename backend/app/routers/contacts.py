"""
Роутер контактов: /api/contacts — CRUD + поиск/фильтрация.
Все маршруты защищены JWT-аутентификацией (get_current_user).
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.user import User
from ..models.contact import ContactCreate, ContactOut, ContactUpdate
from ..repositories import contacts as repo
from ..repositories import events as events_repo
from ..repositories import groups as groups_repo
from ..repositories import interactions as interactions_repo
from ..repositories import reminders as reminders_repo
from ..repositories import questions as questions_repo
from ..repositories import templates as templates_repo
from ..services.attachments import delete_for_contact as delete_attachments
from ..services.fields import FieldValidationError, validate_field_values

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

# Алиас для аннотации зависимости БД
DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
# Алиас для зависимости auth (просто проверяет токен)
AuthDep = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Типизированные поля шаблона
# ---------------------------------------------------------------------------


async def _normalize_fields(db: AsyncIOMotorDatabase, template_id: Optional[str], fields: dict) -> dict:
    """Проверить значения полей по шаблону контакта. 422 — неизвестный шаблон или ошибки в полях."""
    defs = []
    if template_id:
        template = await templates_repo.get_template(db, template_id)
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Шаблон {template_id!r} не найден",
            )
        defs = template.fields
    try:
        return validate_field_values(defs, fields)
    except FieldValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors) from None


async def _check_groups(db: AsyncIOMotorDatabase, group_ids: Optional[list[str]]) -> None:
    """422, если среди group_ids есть несуществующая группа."""
    if not group_ids:
        return
    present = set(await groups_repo.existing_group_ids(db, group_ids))
    missing = [g for g in group_ids if g not in present]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Группы не найдены: {', '.join(missing)}",
        )


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
    await _check_groups(db, data.group_ids)
    fields = await _normalize_fields(db, data.template_id, data.fields)
    return await repo.create_contact(db, data.model_copy(update={"fields": fields}))


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
    template_id: Optional[str] = Query(default=None, description="Фильтр по шаблону карточки"),
    tag: Optional[str] = Query(default=None, description="Фильтр по тегу (без учёта регистра)"),
    group_id: Optional[str] = Query(default=None, description="Фильтр по группе"),
    has_location: Optional[bool] = Query(default=None, description="Только с координатами / только без"),
    sort: Optional[Literal["last_interaction", "name", "created", "importance"]] = Query(
        default=None, description="Сортировка (по умолчанию — недавно изменённые)"
    ),
    skip: int = Query(default=0, ge=0, description="Пропустить N записей"),
    limit: int = Query(default=50, ge=1, le=200, description="Макс. записей в ответе"),
) -> list[ContactOut]:
    """Вернуть список контактов с опциональным поиском и фильтрацией."""
    return await repo.list_contacts(
        db,
        q=q,
        category=category,
        priority=priority,
        template_id=template_id,
        tag=tag,
        group_id=group_id,
        has_location=has_location,
        sort=sort,
        skip=skip,
        limit=limit,
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
    await _check_groups(db, data.group_ids)
    if data.template_id or data.fields is not None:
        current = await repo.get_contact_by_id(db, contact_id)
        if current is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Контакт {contact_id!r} не найден",
            )
        template_id = current.template_id if data.template_id is None else (data.template_id or None)
        fields = data.fields if data.fields is not None else current.fields
        data = data.model_copy(update={"fields": await _normalize_fields(db, template_id, fields)})
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
    """Удалить контакт по ID вместе с вопросами, файлами и напоминаниями. Возвращает 204 No Content при успехе."""
    deleted = await repo.delete_contact(db, contact_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Контакт {contact_id!r} не найден",
        )
    await questions_repo.delete_for_contact(db, contact_id)
    await delete_attachments(db, contact_id)
    await events_repo.unlink_contact(db, contact_id)
    await interactions_repo.unlink_contact(db, contact_id)
    await reminders_repo.delete_for_contact(db, contact_id)
