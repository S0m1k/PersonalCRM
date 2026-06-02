"""
Pydantic v2 модели для контакта.

Структура соответствует «MongoDB: обновлённая модель контакта» из
docs/contact_sync_architecture.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Вспомогательные суб-модели
# ---------------------------------------------------------------------------


class Phone(BaseModel):
    """Телефонный номер с меткой (мобильный, рабочий, домашний, …)."""

    value: str = Field(..., description="Номер телефона")
    label: str = Field(default="телефон", description="Метка (мобильный, рабочий, …)")


class Email(BaseModel):
    """Email-адрес с меткой."""

    value: str = Field(..., description="Email-адрес")
    label: str = Field(default="email", description="Метка (личный, рабочий, …)")


class CustomField(BaseModel):
    """Произвольное поле контакта (ключ–значение)."""

    key: str = Field(..., description="Название поля")
    value: str = Field(default="", description="Значение поля")


class Relationship(BaseModel):
    """Связь с другим контактом в базе."""

    contact_id: str = Field(..., description="ID связанного контакта (строка ObjectId)")
    label: str = Field(default="", description="Характер отношений (коллега, друг, …)")


class ExternalIds(BaseModel):
    """Внешние идентификаторы контакта в сторонних системах."""

    outlook: Optional[str] = None    # Microsoft Graph contact ID
    google: Optional[str] = None     # Google People resourceName
    telegram: Optional[str] = None   # (для будущей интеграции)


# ---------------------------------------------------------------------------
# Базовая и производные модели
# ---------------------------------------------------------------------------


class ContactBase(BaseModel):
    """
    Все редактируемые поля контакта.
    Используется как основа для ContactCreate и ContactUpdate.
    """

    first_name: str = Field(default="", description="Имя")
    last_name: str = Field(default="", description="Фамилия")
    phones: list[Phone] = Field(default_factory=list, description="Список телефонов")
    emails: list[Email] = Field(default_factory=list, description="Список email-адресов")
    company: str = Field(default="", description="Компания / организация")
    position: str = Field(default="", description="Должность")
    city: str = Field(default="", description="Город")
    birthday: Optional[str] = Field(
        default=None,
        description="Дата рождения в формате YYYY-MM-DD",
    )
    notes: str = Field(default="", description="Заметки")
    category: str = Field(default="", description="Категория (например: друг, коллега)")
    priority: str = Field(default="", description="Приоритет (например: high, medium, low)")
    custom_fields: list[CustomField] = Field(
        default_factory=list, description="Произвольные поля"
    )
    relationships: list[Relationship] = Field(
        default_factory=list, description="Связи с другими контактами"
    )
    external_ids: ExternalIds = Field(
        default_factory=ExternalIds,
        description="Внешние ID для синхронизации",
    )

    @field_validator("birthday", mode="before")
    @classmethod
    def validate_birthday(cls, v: Any) -> Optional[str]:
        """Принимаем None или строку формата YYYY-MM-DD. Пустую строку→None."""
        if v == "" or v is None:
            return None
        # Минимальная проверка формата
        if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
            return v
        raise ValueError("birthday должен быть в формате YYYY-MM-DD или null")


class ContactCreate(ContactBase):
    """Данные для создания нового контакта. source указывает происхождение."""

    source: str = Field(
        default="manual",
        description='Источник: "manual" | "outlook" | "google" | "csv" | "vcard" | "telegram"',
    )
    sources: list[str] = Field(default_factory=list, description="Все источники после merge")


class ContactUpdate(BaseModel):
    """
    Частичное обновление контакта (PATCH).
    Все поля опциональны — передаём только то, что меняем.
    """

    model_config = ConfigDict(extra="ignore")

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phones: Optional[list[Phone]] = None
    emails: Optional[list[Email]] = None
    company: Optional[str] = None
    position: Optional[str] = None
    city: Optional[str] = None
    birthday: Optional[str] = None
    notes: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    custom_fields: Optional[list[CustomField]] = None
    relationships: Optional[list[Relationship]] = None
    external_ids: Optional[ExternalIds] = None
    source: Optional[str] = None
    sources: Optional[list[str]] = None

    @field_validator("birthday", mode="before")
    @classmethod
    def validate_birthday(cls, v: Any) -> Optional[str]:
        if v == "" or v is None:
            return None
        if isinstance(v, str) and len(v) == 10 and v[4] == "-" and v[7] == "-":
            return v
        raise ValueError("birthday должен быть в формате YYYY-MM-DD или null")


class ContactOut(ContactBase):
    """
    Контакт, возвращаемый клиенту.
    Содержит id (строка из Mongo _id), source, sources и временны́е метки.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="ID контакта (строка ObjectId)")
    source: str = Field(default="manual")
    sources: list[str] = Field(default_factory=list)
    last_synced_at: Optional[datetime] = None
    sync_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "ContactOut":
        """
        Конвертируем документ MongoDB (с _id: ObjectId) в ContactOut.
        _id → id (str), вложенные словари → суб-модели.
        """
        data = dict(doc)
        data["id"] = str(data.pop("_id"))

        # MongoDB (и mongomock) хранят datetime как naive UTC. Приводим к
        # tz-aware, чтобы значения из create (in-memory) и из БД были сравнимы.
        for ts_field in ("created_at", "updated_at", "last_synced_at"):
            val = data.get(ts_field)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts_field] = val.replace(tzinfo=timezone.utc)

        # ExternalIds может прийти как dict
        if isinstance(data.get("external_ids"), dict):
            data["external_ids"] = ExternalIds(**data["external_ids"])

        # Списки суб-моделей
        if data.get("phones"):
            data["phones"] = [
                Phone(**p) if isinstance(p, dict) else p for p in data["phones"]
            ]
        if data.get("emails"):
            data["emails"] = [
                Email(**e) if isinstance(e, dict) else e for e in data["emails"]
            ]
        if data.get("custom_fields"):
            data["custom_fields"] = [
                CustomField(**cf) if isinstance(cf, dict) else cf
                for cf in data["custom_fields"]
            ]
        if data.get("relationships"):
            data["relationships"] = [
                Relationship(**r) if isinstance(r, dict) else r
                for r in data["relationships"]
            ]

        return cls(**data)
