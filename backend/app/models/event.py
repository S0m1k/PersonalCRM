"""
Pydantic-модели событий календаря (коллекция events в базе пользователя).

Время хранится в UTC; timezone — часовой пояс, в котором событие создано
(IANA, например Europe/Moscow): в нём наивное время из формы переводится в UTC.
Событие на весь день: start — полночь первого дня, end — полночь дня ПОСЛЕ
последнего (как в Google Calendar и Microsoft Graph), оба в UTC.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EventSource = Literal["crm", "microsoft", "google"]

TITLE_MAX = 300
DESCRIPTION_MAX = 20_000
ATTENDEES_MAX = 200


def check_timezone(value: Any) -> str:
    if value in (None, ""):
        return "UTC"
    try:
        ZoneInfo(str(value))
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("timezone: часовой пояс IANA, например Europe/Moscow") from None
    return str(value)


def to_utc(value: datetime, tz_name: str) -> datetime:
    """Наивное время — в поясе события, с поясом — как есть; результат в UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(tz_name))
    return value.astimezone(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Время из MongoDB приходит без пояса, но хранится в UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def day_start(value: datetime) -> datetime:
    """Полночь (UTC) дня, на который приходится value в его собственном поясе."""
    return datetime.combine(value.date(), time.min, tzinfo=timezone.utc)


class Attendee(BaseModel):
    email: str = Field(default="", max_length=320)
    name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=50)
    # accepted / declined / tentative / needsAction / none — как отдаёт провайдер
    response: str = Field(default="", max_length=30)

    @field_validator("email", mode="before")
    @classmethod
    def _norm_email(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value


class _EventFields(BaseModel):
    title: str = Field(default="", max_length=TITLE_MAX)
    location: str = Field(default="", max_length=500)
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    attendees: list[Attendee] = Field(default_factory=list, max_length=ATTENDEES_MAX)
    contact_ids: list[str] = Field(default_factory=list, max_length=ATTENDEES_MAX)
    # Дописывать открытые вопросы «на встрече» в описание у провайдера (по желанию)
    push_questions: bool = False

    @field_validator("title", "location", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class EventCreate(_EventFields):
    title: str = Field(..., min_length=1, max_length=TITLE_MAX)
    start: datetime
    end: Optional[datetime] = None
    all_day: bool = False
    timezone: str = "UTC"
    # Сразу создать событие у провайдера этого подключения (Outlook / Google)
    connection_id: Optional[str] = None

    _tz = field_validator("timezone", mode="before")(check_timezone)

    @model_validator(mode="after")
    def _normalize_times(self) -> "EventCreate":
        start, end = normalize_range(self.start, self.end, self.all_day, self.timezone)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        return self


class EventUpdate(BaseModel):
    """Частичное изменение. Время пересчитывается вместе (start/end/all_day/timezone)."""

    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = Field(default=None, min_length=1, max_length=TITLE_MAX)
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    all_day: Optional[bool] = None
    timezone: Optional[str] = None
    location: Optional[str] = Field(default=None, max_length=500)
    description: Optional[str] = Field(default=None, max_length=DESCRIPTION_MAX)
    attendees: Optional[list[Attendee]] = Field(default=None, max_length=ATTENDEES_MAX)
    contact_ids: Optional[list[str]] = Field(default=None, max_length=ATTENDEES_MAX)
    push_questions: Optional[bool] = None

    @field_validator("title", "location", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("timezone", mode="before")
    @classmethod
    def _tz(cls, value: Any) -> Any:
        return None if value is None else check_timezone(value)


def normalize_range(
    start: datetime, end: Optional[datetime], all_day: bool, tz_name: str
) -> tuple[datetime, datetime]:
    """
    Привести начало и конец к UTC. Без конца — час (или один день для «весь день»).
    Для «весь день» берутся только даты: [первый день, день после последнего).
    """
    if all_day:
        first = day_start(start)
        last = day_start(end) if end is not None else first
        if last <= first:
            last = first + timedelta(days=1)
        return first, last
    start_utc = to_utc(start, tz_name)
    end_utc = to_utc(end, tz_name) if end is not None else start_utc + timedelta(hours=1)
    if end_utc < start_utc:
        raise ValueError("Конец события раньше начала")
    return start_utc, end_utc


class ContactBrief(BaseModel):
    id: str
    name: str


class EventQuestion(BaseModel):
    id: str
    contact_id: str
    contact_name: str = ""
    text: str


class EventOut(BaseModel):
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    timezone: str = "UTC"
    location: str = ""
    description: str = ""
    attendees: list[Attendee] = Field(default_factory=list)
    contact_ids: list[str] = Field(default_factory=list)
    contacts: list[ContactBrief] = Field(default_factory=list)
    # Открытые вопросы «на встрече» к привязанным людям
    questions: list[EventQuestion] = Field(default_factory=list)
    push_questions: bool = False
    source: EventSource = "crm"
    connection_id: Optional[str] = None
    external_id: Optional[str] = None
    web_link: str = ""
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict, **extra: Any) -> "EventOut":
        data = {k: v for k, v in doc.items() if k in cls.model_fields or k == "_id"}
        data["id"] = str(data.pop("_id"))
        for ts in ("start", "end", "created_at", "updated_at"):
            val = data.get(ts)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts] = val.replace(tzinfo=timezone.utc)
        return cls(**{**data, **extra})
