"""
Pydantic-модели напоминаний (коллекция reminders).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReminderRepeat = Literal["none", "weekly", "monthly", "yearly"]
ReminderStatus = Literal["open", "done", "all"]

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check_date(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise ValueError("Дата в формате ГГГГ-ММ-ДД") from None
    return value


def _check_time(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or not _TIME_RE.match(value):
        raise ValueError("Время в формате ЧЧ:ММ")
    return value


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class ReminderCreate(BaseModel):
    contact_id: Optional[str] = None
    title: str = Field(..., min_length=1, max_length=300)
    note: str = Field(default="", max_length=2000)
    due_date: str
    due_time: Optional[str] = None
    repeat: ReminderRepeat = "none"

    _strip_title = field_validator("title", mode="before")(_strip)
    _date = field_validator("due_date", mode="before")(_check_date)
    _time = field_validator("due_time", mode="before")(_check_time)


class ReminderUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    contact_id: Optional[str] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=300)
    note: Optional[str] = Field(default=None, max_length=2000)
    due_date: Optional[str] = None
    due_time: Optional[str] = None
    repeat: Optional[ReminderRepeat] = None

    _strip_title = field_validator("title", mode="before")(_strip)
    _date = field_validator("due_date", mode="before")(_check_date)
    _time = field_validator("due_time", mode="before")(_check_time)


class ReminderOut(BaseModel):
    id: str
    contact_id: Optional[str] = None
    contact_name: str = ""
    title: str
    note: str = ""
    due_date: str
    due_time: Optional[str] = None
    repeat: ReminderRepeat = "none"
    done_at: Optional[datetime] = None
    created_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict, contact_name: str = "") -> "ReminderOut":
        data = {k: v for k, v in doc.items() if k != "_id"}
        data["id"] = str(doc["_id"])
        data["contact_name"] = contact_name
        for ts in ("created_at", "done_at"):
            val = data.get(ts)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts] = val.replace(tzinfo=timezone.utc)
        return cls(**data)
