"""
Сохранённые виды списка контактов (коллекция views): имя + фильтры + сортировка + колонки.
Фильтры хранятся как есть — это параметры списка /api/contacts, которые понимает фронт.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAME_MAX = 100
SortKey = Literal["last_interaction", "name", "created", "importance"]


class _ViewFields(BaseModel):
    @field_validator("name", "emoji", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class ViewCreate(_ViewFields):
    name: str = Field(..., min_length=1, max_length=NAME_MAX)
    emoji: str = Field(default="", max_length=16)
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: Optional[SortKey] = None
    columns: list[str] = Field(default_factory=list, max_length=30)


class ViewUpdate(_ViewFields):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(default=None, min_length=1, max_length=NAME_MAX)
    emoji: Optional[str] = Field(default=None, max_length=16)
    filters: Optional[dict[str, Any]] = None
    sort: Optional[SortKey] = None
    columns: Optional[list[str]] = Field(default=None, max_length=30)


class ViewOut(BaseModel):
    id: str
    name: str
    emoji: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    sort: Optional[SortKey] = None
    columns: list[str] = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "ViewOut":
        created = doc.get("created_at")
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return cls(
            id=str(doc["_id"]),
            name=doc.get("name", ""),
            emoji=doc.get("emoji", ""),
            filters=doc.get("filters") or {},
            sort=doc.get("sort"),
            columns=doc.get("columns") or [],
            created_at=created,
        )
