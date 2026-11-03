"""
Взаимодействия (Timeline): заметка, звонок, встреча, сообщение — с одним или несколькими людьми.
Коллекция interactions в базе пользователя. Прошедшие события календаря в ленту подмешиваются
при чтении (include_events) и в этой коллекции не хранятся.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

InteractionKind = Literal["note", "call", "meeting", "message", "email", "other"]
InteractionSource = Literal["manual", "calendar", "ai", "import"]

TITLE_MAX = 300
BODY_MAX = 20_000
CONTACTS_MAX = 50


def to_aware_utc(value: datetime) -> datetime:
    """Наивное время считаем UTC (так хранит Mongo), с поясом — переводим в UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class _InteractionFields(BaseModel):
    @field_validator("title", "body", mode="before", check_fields=False)
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v

    @field_validator("contact_ids", mode="before", check_fields=False)
    @classmethod
    def _unique_ids(cls, v: Any) -> Any:
        return list(dict.fromkeys(str(c) for c in v)) if isinstance(v, (list, tuple)) else v

    @field_validator("occurred_at", mode="after", check_fields=False)
    @classmethod
    def _utc(cls, v: Optional[datetime]) -> Optional[datetime]:
        return to_aware_utc(v) if v is not None else None


class InteractionCreate(_InteractionFields):
    contact_ids: list[str] = Field(default_factory=list, max_length=CONTACTS_MAX)
    kind: InteractionKind = "note"
    title: str = Field(default="", max_length=TITLE_MAX)
    body: str = Field(default="", max_length=BODY_MAX)
    occurred_at: Optional[datetime] = Field(default=None, description="По умолчанию — сейчас")
    source: InteractionSource = "manual"


class InteractionUpdate(_InteractionFields):
    model_config = ConfigDict(extra="ignore")

    contact_ids: Optional[list[str]] = Field(default=None, max_length=CONTACTS_MAX)
    kind: Optional[InteractionKind] = None
    title: Optional[str] = Field(default=None, max_length=TITLE_MAX)
    body: Optional[str] = Field(default=None, max_length=BODY_MAX)
    occurred_at: Optional[datetime] = None


class InteractionOut(BaseModel):
    # У элементов из календаря id = "event:<id события>"
    id: str
    contact_ids: list[str] = Field(default_factory=list)
    kind: InteractionKind = "note"
    title: str = ""
    body: str = ""
    occurred_at: datetime
    source: InteractionSource = "manual"
    # Элементы из календаря менять здесь нельзя — только в календаре
    read_only: bool = False
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "InteractionOut":
        data: dict[str, Any] = {
            k: doc[k] for k in ("contact_ids", "kind", "title", "body", "occurred_at", "source") if k in doc
        }
        for ts in ("occurred_at", "created_at", "updated_at"):
            value = doc.get(ts)
            if isinstance(value, datetime):
                data[ts] = to_aware_utc(value)
        return cls(id=str(doc["_id"]), **data)

    @classmethod
    def from_event(cls, doc: dict) -> "InteractionOut":
        start = to_aware_utc(doc["start"])
        return cls(
            id=f"event:{doc['_id']}",
            contact_ids=list(doc.get("contact_ids") or []),
            kind="meeting",
            title=doc.get("title", ""),
            body=doc.get("location", ""),
            occurred_at=start,
            source="calendar",
            read_only=True,
            created_at=to_aware_utc(doc.get("created_at") or start),
            updated_at=to_aware_utc(doc.get("updated_at") or start),
        )


class InteractionPage(BaseModel):
    items: list[InteractionOut]
    # Передать в ?cursor=, чтобы получить следующую страницу; null — конец ленты
    next_cursor: Optional[str] = None
