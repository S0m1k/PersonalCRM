"""
Группы контактов (коллекция groups в базе пользователя): «Семья», «Коллеги», «Клуб бега».
Контакт хранит id групп в group_ids; число участников считается при выдаче.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAME_MAX = 100


class _GroupFields(BaseModel):
    @field_validator("name", "emoji", "color", "description", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class GroupCreate(_GroupFields):
    name: str = Field(..., min_length=1, max_length=NAME_MAX)
    emoji: str = Field(default="", max_length=16)
    # Токен акцента или #rrggbb — как решит фронт
    color: str = Field(default="", max_length=32)
    description: str = Field(default="", max_length=500)


class GroupUpdate(_GroupFields):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(default=None, min_length=1, max_length=NAME_MAX)
    emoji: Optional[str] = Field(default=None, max_length=16)
    color: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = Field(default=None, max_length=500)


class GroupOut(BaseModel):
    id: str
    name: str
    emoji: str = ""
    color: str = ""
    description: str = ""
    member_count: int = 0
    created_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict, member_count: int = 0) -> "GroupOut":
        created = doc.get("created_at")
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return cls(
            id=str(doc["_id"]),
            name=doc.get("name", ""),
            emoji=doc.get("emoji", ""),
            color=doc.get("color", ""),
            description=doc.get("description", ""),
            member_count=member_count,
            created_at=created,
        )
