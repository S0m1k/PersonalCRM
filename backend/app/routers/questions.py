"""
Роутер вопросов к человеку: /api/questions.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.user import User
from ..models.question import QuestionCreate, QuestionOut, QuestionStatus, QuestionUpdate
from ..repositories import contacts as contacts_repo
from ..repositories import questions as repo

router = APIRouter(prefix="/api/questions", tags=["questions"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _not_found(question_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Вопрос {question_id!r} не найден")


@router.get("", response_model=list[QuestionOut], summary="Список вопросов")
async def list_questions(
    db: DbDep,
    _user: AuthDep,
    status_: Optional[QuestionStatus] = Query(default=None, alias="status"),
    contact_id: Optional[str] = Query(default=None),
) -> list[QuestionOut]:
    return await repo.list_questions(db, status=status_, contact_id=contact_id)


@router.get("/open-counts", response_model=dict[str, int], summary="Открытые вопросы по контактам")
async def open_counts(db: DbDep, _user: AuthDep) -> dict[str, int]:
    return await repo.open_counts(db)


@router.post("", response_model=QuestionOut, status_code=status.HTTP_201_CREATED, summary="Добавить вопрос")
async def create_question(data: QuestionCreate, db: DbDep, _user: AuthDep) -> QuestionOut:
    if await contacts_repo.get_contact_by_id(db, data.contact_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден")
    return await repo.create_question(db, data)


@router.patch("/{question_id}", response_model=QuestionOut, summary="Изменить / ответить на вопрос")
async def update_question(question_id: str, data: QuestionUpdate, db: DbDep, _user: AuthDep) -> QuestionOut:
    question = await repo.update_question(db, question_id, data)
    if question is None:
        raise _not_found(question_id)
    return question


@router.delete(
    "/{question_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Удалить вопрос"
)
async def delete_question(question_id: str, db: DbDep, _user: AuthDep) -> None:
    if not await repo.delete_question(db, question_id):
        raise _not_found(question_id)
