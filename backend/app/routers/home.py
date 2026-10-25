"""
Роутер главной страницы: /api/home — сводка на сегодня.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.user import User
from ..repositories import questions as questions_repo
from ..services.birthdays import upcoming_birthdays

router = APIRouter(prefix="/api/home", tags=["home"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

CONTACTS = "contacts"
BIRTHDAY_WINDOW_DAYS = 14
RECENT_LIMIT = 8
QUESTIONS_LIMIT = 8

_BRIEF = {"first_name": 1, "last_name": 1, "company": 1, "position": 1, "birthday": 1, "template_id": 1}


def _name(doc: dict) -> str:
    return " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip()


@router.get("", summary="Сводка для главной страницы")
async def home(
    db: DbDep,
    _user: AuthDep,
    today: Optional[date] = Query(default=None, description="Локальная дата пользователя (сервер может жить в UTC)"),
) -> dict:
    with_birthday = await db[CONTACTS].find({"birthday": {"$nin": [None, ""]}}, _BRIEF).to_list(length=None)
    birthdays = upcoming_birthdays(
        [{"id": str(d["_id"]), "name": _name(d), "birthday": d.get("birthday")} for d in with_birthday],
        today or date.today(),
        BIRTHDAY_WINDOW_DAYS,
    )

    recent_docs = await db[CONTACTS].find({}, _BRIEF).sort("updated_at", -1).limit(RECENT_LIMIT).to_list(
        length=RECENT_LIMIT
    )
    recent = [
        {
            "id": str(d["_id"]),
            "name": _name(d),
            "company": d.get("company", ""),
            "position": d.get("position", ""),
            "template_id": d.get("template_id"),
        }
        for d in recent_docs
    ]

    open_questions = await questions_repo.list_questions(db, status="open")
    return {
        "stats": {
            "contacts": await db[CONTACTS].count_documents({}),
            "open_questions": len(open_questions),
        },
        "birthdays": birthdays,
        "recent": recent,
        "open_questions": [q.model_dump(mode="json") for q in open_questions[-QUESTIONS_LIMIT:][::-1]],
    }
