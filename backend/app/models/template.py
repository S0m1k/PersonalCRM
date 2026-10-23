"""
Pydantic-модели шаблонов карточек: набор типизированных полей для группы контактов
(«Клиент», «Партнёр», «Друг», …).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FieldType = Literal["text", "longtext", "date", "number", "select", "url", "bool"]

MAX_FIELDS = 40

# Иконки шаблонов — имена SVG-иконок lucide (фронтенд держит такой же список)
TEMPLATE_ICONS = (
    "file-text", "briefcase", "handshake", "smile", "house", "id-card", "heart", "star",
    "users", "building", "graduation-cap", "stethoscope", "wrench", "plane", "gem",
    "coins", "rocket", "scale", "palette", "dumbbell",
)
DEFAULT_ICON = "file-text"

# Шаблоны, созданные до перехода на SVG, хранят эмодзи
_LEGACY_EMOJI = {"💼": "briefcase", "🤝": "handshake", "🙂": "smile", "🏠": "house", "🧑‍💼": "id-card", "📄": "file-text"}


def _check_icon(value: Optional[str]) -> Optional[str]:
    if value is not None and value not in TEMPLATE_ICONS:
        raise ValueError(f"Неизвестная иконка {value!r}. Доступны: {', '.join(TEMPLATE_ICONS)}")
    return value


class FieldDef(BaseModel):
    """Описание одного поля шаблона. key стабилен при переименовании label."""

    key: str = Field(default="", max_length=40, pattern=r"^[a-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=60)
    type: FieldType = "text"
    options: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _select_needs_options(self) -> "FieldDef":
        if self.type == "select" and not self.options:
            raise ValueError(f"Поле «{self.label}»: у списка должны быть варианты")
        return self


def _check_unique_keys(fields: list[FieldDef]) -> list[FieldDef]:
    keys = [f.key for f in fields if f.key]
    if len(keys) != len(set(keys)):
        raise ValueError("Ключи полей шаблона должны быть уникальными")
    return fields


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    icon: str = DEFAULT_ICON
    fields: list[FieldDef] = Field(default_factory=list, max_length=MAX_FIELDS)

    _icon = field_validator("icon")(_check_icon)

    @model_validator(mode="after")
    def _unique_keys(self) -> "TemplateCreate":
        _check_unique_keys(self.fields)
        return self


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(default=None, min_length=1, max_length=60)
    icon: Optional[str] = None
    fields: Optional[list[FieldDef]] = Field(default=None, max_length=MAX_FIELDS)

    _icon = field_validator("icon")(_check_icon)

    @model_validator(mode="after")
    def _unique_keys(self) -> "TemplateUpdate":
        if self.fields is not None:
            _check_unique_keys(self.fields)
        return self


class TemplateOut(BaseModel):
    id: str
    name: str
    icon: str
    fields: list[FieldDef]
    builtin: bool = False
    created_at: datetime
    updated_at: datetime

    @field_validator("icon", mode="before")
    @classmethod
    def _legacy_icon(cls, value: object) -> str:
        if value in TEMPLATE_ICONS:
            return str(value)
        return _LEGACY_EMOJI.get(str(value), DEFAULT_ICON)

    @classmethod
    def from_mongo(cls, doc: dict) -> "TemplateOut":
        data = dict(doc)
        data["id"] = str(data.pop("_id"))
        for ts in ("created_at", "updated_at"):
            val = data.get(ts)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts] = val.replace(tzinfo=timezone.utc)
        return cls(**data)
