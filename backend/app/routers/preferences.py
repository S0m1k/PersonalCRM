"""
Роутер настроек пользователя: /api/preferences/priority-labels — названия уровней Priority Map.
Хранится в коллекции preferences (по одному документу на настройку) в базе пользователя.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth import get_current_user, get_user_db
from ..models.user import User

router = APIRouter(prefix="/api/preferences", tags=["preferences"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

COLLECTION = "preferences"
PRIORITY_LABELS_ID = "priority_labels"
LABEL_MAX_LEN = 24
DEFAULT_PRIORITY_LABELS = {"top": "Топ", "high": "Высокий", "medium": "Средний", "low": "Низкий", "none": "Нет"}


class PriorityLabels(BaseModel):
    """Все пять уровней обязательны; пустая подпись = «вернуть стандартную»."""

    model_config = ConfigDict(extra="forbid")

    top: str = Field(..., max_length=LABEL_MAX_LEN)
    high: str = Field(..., max_length=LABEL_MAX_LEN)
    medium: str = Field(..., max_length=LABEL_MAX_LEN)
    low: str = Field(..., max_length=LABEL_MAX_LEN)
    none: str = Field(..., max_length=LABEL_MAX_LEN)

    @field_validator("top", "high", "medium", "low", "none", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def _effective(stored: dict | None) -> dict[str, str]:
    stored = stored or {}
    return {key: (stored.get(key) or "").strip() or default for key, default in DEFAULT_PRIORITY_LABELS.items()}


@router.get("/priority-labels", response_model=PriorityLabels, summary="Названия уровней Priority Map")
async def get_priority_labels(db: DbDep, _user: AuthDep) -> dict[str, str]:
    doc = await db[COLLECTION].find_one({"_id": PRIORITY_LABELS_ID})
    return _effective(doc.get("labels") if doc else None)


@router.put("/priority-labels", response_model=PriorityLabels, summary="Переименовать уровни Priority Map")
async def put_priority_labels(data: PriorityLabels, db: DbDep, _user: AuthDep) -> dict[str, str]:
    labels = data.model_dump()
    await db[COLLECTION].replace_one({"_id": PRIORITY_LABELS_ID}, {"_id": PRIORITY_LABELS_ID, "labels": labels}, upsert=True)
    return _effective(labels)
