"""
Роутер шаблонов карточек: /api/templates — CRUD.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.user import User
from ..models.template import TemplateCreate, TemplateOut, TemplateUpdate
from ..repositories import templates as repo

router = APIRouter(prefix="/api/templates", tags=["templates"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _not_found(template_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Шаблон {template_id!r} не найден")


@router.get("", response_model=list[TemplateOut], summary="Список шаблонов карточек")
async def list_templates(db: DbDep, _user: AuthDep) -> list[TemplateOut]:
    return await repo.list_templates(db)


@router.get("/{template_id}", response_model=TemplateOut, summary="Шаблон по ID")
async def get_template(template_id: str, db: DbDep, _user: AuthDep) -> TemplateOut:
    template = await repo.get_template(db, template_id)
    if template is None:
        raise _not_found(template_id)
    return template


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED, summary="Создать шаблон")
async def create_template(data: TemplateCreate, db: DbDep, _user: AuthDep) -> TemplateOut:
    return await repo.create_template(db, data)


@router.patch("/{template_id}", response_model=TemplateOut, summary="Изменить шаблон")
async def update_template(template_id: str, data: TemplateUpdate, db: DbDep, _user: AuthDep) -> TemplateOut:
    template = await repo.update_template(db, template_id, data)
    if template is None:
        raise _not_found(template_id)
    return template


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Удалить шаблон (если им не пользуется ни один контакт)",
)
async def delete_template(template_id: str, db: DbDep, _user: AuthDep) -> None:
    in_use = await repo.count_usage(db, template_id)
    if in_use:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Шаблоном пользуются контакты ({in_use}). Сначала смените им шаблон.",
        )
    if not await repo.delete_template(db, template_id):
        raise _not_found(template_id)
