"""
Слияние дублей: /api/contacts/duplicates, /api/contacts/duplicates/dismiss, /api/contacts/merge.
Подключается раньше роутера контактов — иначе /{contact_id} перехватит эти пути.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field, model_validator

from ..auth import get_current_user, get_user_db
from ..models.contact import ContactOut
from ..models.user import User
from ..services import duplicates as service

router = APIRouter(prefix="/api/contacts", tags=["duplicates"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


class DuplicatePair(BaseModel):
    a: ContactOut
    b: ContactOut
    score: int
    reasons: list[str]


class DismissIn(BaseModel):
    a_id: str
    b_id: str

    @model_validator(mode="after")
    def _different(self) -> "DismissIn":
        if self.a_id == self.b_id:
            raise ValueError("нужны два разных контакта")
        return self


class MergeIn(BaseModel):
    keep_id: str
    merge_ids: list[str] = Field(..., min_length=1, max_length=50)

    @model_validator(mode="after")
    def _not_self(self) -> "MergeIn":
        if self.keep_id in self.merge_ids:
            raise ValueError("оставляемый контакт нельзя сливать с самим собой")
        return self


@router.get("/duplicates", response_model=list[DuplicatePair], summary="Предложения дублей")
async def list_duplicates(db: DbDep, _user: AuthDep) -> list[DuplicatePair]:
    pairs = await service.suggest(db)
    return [
        DuplicatePair(
            a=ContactOut.from_mongo(p["a"]), b=ContactOut.from_mongo(p["b"]), score=p["score"], reasons=p["reasons"]
        )
        for p in pairs
    ]


@router.post(
    "/duplicates/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Не дубли: больше не предлагать пару",
)
async def dismiss_pair(data: DismissIn, db: DbDep, _user: AuthDep) -> None:
    await service.dismiss(db, data.a_id, data.b_id)


@router.post("/merge", response_model=ContactOut, summary="Объединить контакты")
async def merge_contacts(data: MergeIn, db: DbDep, _user: AuthDep) -> ContactOut:
    doc = await service.merge(db, data.keep_id, data.merge_ids)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Один из контактов не найден")
    return ContactOut.from_mongo(doc)
