"""
Pydantic-модели вопросов к человеку («что хочу спросить» и ответ).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

QuestionStatus = Literal["open", "answered", "dropped"]
QuestionSource = Literal["manual", "ai", "meeting"]


def _check_ask_at(value: Any) -> Optional[str]:
    """None, "next_meeting" или дата ГГГГ-ММ-ДД."""
    if value in (None, ""):
        return None
    if value == "next_meeting":
        return value
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError('ask_at: "next_meeting" или дата ГГГГ-ММ-ДД') from None


def _strip_text(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class QuestionCreate(BaseModel):
    contact_id: str
    text: str = Field(..., min_length=1, max_length=500)
    ask_at: Optional[str] = None
    source: QuestionSource = "manual"

    _strip = field_validator("text", mode="before")(_strip_text)
    _ask_at = field_validator("ask_at", mode="before")(_check_ask_at)


class QuestionUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    status: Optional[QuestionStatus] = None
    answer: Optional[str] = Field(default=None, max_length=5000)
    ask_at: Optional[str] = None

    _strip = field_validator("text", mode="before")(_strip_text)
    _ask_at = field_validator("ask_at", mode="before")(_check_ask_at)


class QuestionOut(BaseModel):
    id: str
    contact_id: str
    contact_name: str = ""
    text: str
    status: QuestionStatus
    answer: str = ""
    answered_at: Optional[datetime] = None
    ask_at: Optional[str] = None
    source: QuestionSource = "manual"
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict, contact_name: str = "") -> "QuestionOut":
        data = dict(doc)
        data["id"] = str(data.pop("_id"))
        data["contact_name"] = contact_name
        for ts in ("created_at", "updated_at", "answered_at"):
            val = data.get(ts)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts] = val.replace(tzinfo=timezone.utc)
        return cls(**data)
