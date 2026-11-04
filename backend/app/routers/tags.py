"""
Роутер тегов: /api/tags — теги со счётчиками, переименование / слияние, удаление у всех контактов.
Отдельной коллекции нет: теги живут в contacts.tags.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field

from ..auth import get_current_user, get_user_db
from ..models.contact import TAG_MAX_LEN
from ..models.user import User
from ..repositories import contacts as contacts_repo

router = APIRouter(prefix="/api/tags", tags=["tags"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


class TagCount(BaseModel):
    tag: str
    count: int


class TagRename(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # from — служебное слово Python, поэтому from_ с алиасом
    from_: str = Field(..., alias="from", min_length=1, max_length=TAG_MAX_LEN)
    to: str = Field(..., min_length=1, max_length=TAG_MAX_LEN)


class TagChange(BaseModel):
    updated: int


@router.get("", response_model=list[TagCount], summary="Теги и число контактов")
async def list_tags(db: DbDep, _user: AuthDep) -> list[dict]:
    return await contacts_repo.tag_counts(db)


@router.post("/rename", response_model=TagChange, summary="Переименовать тег (если новый уже есть — слить)")
async def rename_tag(data: TagRename, db: DbDep, _user: AuthDep) -> TagChange:
    old, new = data.from_.strip(), data.to.strip()
    if not old or not new:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Тег не может быть пустым")
    return TagChange(updated=await contacts_repo.rewrite_tag(db, old, new))


@router.delete("/{tag:path}", response_model=TagChange, summary="Убрать тег у всех контактов")
async def delete_tag(tag: str, db: DbDep, _user: AuthDep) -> TagChange:
    return TagChange(updated=await contacts_repo.rewrite_tag(db, tag, None))
