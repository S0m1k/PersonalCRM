"""
Pydantic v2 модели для контакта.

Структура соответствует «MongoDB: обновлённая модель контакта» из
docs/contact_sync_architecture.md.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..services.phones import phone_key


# ---------------------------------------------------------------------------
# Вспомогательные суб-модели
# ---------------------------------------------------------------------------


class Phone(BaseModel):
    """Телефонный номер с меткой (мобильный, рабочий, домашний, …)."""

    value: str = Field(..., description="Номер телефона")
    label: str = Field(default="телефон", description="Метка (мобильный, рабочий, …)")
    # Ключ для сравнения: +79215535333 для 8 (921) 553-53-33 и любой другой записи того же номера.
    # Всегда вычисляется из value — присланное клиентом значение игнорируется.
    normalized: str = Field(default="", description="Номер в E.164 (или только цифры), вычисляется сервером")

    @model_validator(mode="after")
    def _normalize(self) -> "Phone":
        self.normalized = phone_key(self.value)
        return self


def dedupe_phones(phones: list[Phone]) -> list[Phone]:
    """Один номер в разных записях (89…, +79…) — оставить первую."""
    seen: set[str] = set()
    result: list[Phone] = []
    for phone in phones:
        key = phone.normalized or phone.value.strip()
        if key and key in seen:
            continue
        seen.add(key)
        result.append(phone)
    return result


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
# Sprint 11: теги, соцсети, keep in touch, место
# ---------------------------------------------------------------------------

TAG_MAX_LEN = 50
TAGS_MAX = 50
FREQUENCY_MIN_DAYS = 1
FREQUENCY_MAX_DAYS = 730
SOCIAL_MAX_LEN = 300
_HANDLE_RE = re.compile(r"^@?[\w.\-]{1,100}$")
_URL_RE = re.compile(r"^https?://[^\s<>\"']{1,%d}$" % SOCIAL_MAX_LEN, re.IGNORECASE)


def normalize_labels(value: Any) -> list[str]:
    """Теги / сферы жизни: trim, без пустых, без повторов (без учёта регистра), ≤50 символов, ≤50 штук."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError("ожидается список строк")
    seen: set[str] = set()
    result: list[str] = []
    for raw in value:
        item = str(raw).strip()
        if not item:
            continue
        if len(item) > TAG_MAX_LEN:
            raise ValueError(f"тег длиннее {TAG_MAX_LEN} символов")
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    if len(result) > TAGS_MAX:
        raise ValueError(f"не больше {TAGS_MAX} элементов")
    return result


def check_iso_date(value: Any, name: str) -> Optional[str]:
    """None / "" → None; дата или строка YYYY-MM-DD → строка YYYY-MM-DD (в Mongo даты храним строками)."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise ValueError(f"{name} должен быть датой YYYY-MM-DD или null") from None


class KeepInTouch(BaseModel):
    """Как часто хочется общаться; snoozed_until — напоминание отложено до даты (включительно)."""

    frequency_days: Optional[int] = Field(default=None, ge=FREQUENCY_MIN_DAYS, le=FREQUENCY_MAX_DAYS)
    snoozed_until: Optional[str] = None

    @field_validator("snoozed_until", mode="before")
    @classmethod
    def _date(cls, v: Any) -> Optional[str]:
        return check_iso_date(v, "snoozed_until")


class Location(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)
    label: str = Field(default="", max_length=200)


class Social(BaseModel):
    """Соцсети: http(s)-ссылка или ник (@name). Другие схемы (javascript:, data:) отклоняются."""

    linkedin: str = ""
    facebook: str = ""
    instagram: str = ""
    telegram: str = ""
    twitter: str = ""
    website: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _link(cls, v: Any) -> str:
        if v is None:
            return ""
        text = str(v).strip()
        if not text:
            return ""
        if _URL_RE.match(text) or _HANDLE_RE.match(text):
            return text
        raise ValueError("ожидается http(s)-ссылка или ник")


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
    template_id: Optional[str] = Field(default=None, description="ID шаблона карточки")
    fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Значения типизированных полей шаблона: {ключ поля: значение}",
    )
    description: str = Field(default="", max_length=2000, description="Короткое описание (био), отдельно от заметок")
    tags: list[str] = Field(default_factory=list, description="Теги")
    group_ids: list[str] = Field(default_factory=list, description="ID групп")
    keep_in_touch: KeepInTouch = Field(default_factory=KeepInTouch, description="Частота общения")
    first_met_at: Optional[str] = Field(default=None, description="Когда познакомились, YYYY-MM-DD")
    first_met_note: str = Field(default="", max_length=1000, description="Где / как познакомились")
    address: str = Field(default="", max_length=500, description="Адрес")
    location: Optional[Location] = Field(default=None, description="Координаты для карты")
    social: Social = Field(default_factory=Social, description="Соцсети")
    importance: Optional[int] = Field(default=None, ge=1, le=5, description="Важность 1..5 (ось Priority Map)")
    closeness: Optional[int] = Field(default=None, ge=1, le=5, description="Близость 1..5 (ось Priority Map)")
    life_areas: list[str] = Field(default_factory=list, description="Сферы жизни (колесо баланса)")

    @field_validator("tags", "life_areas", mode="before")
    @classmethod
    def _labels(cls, v: Any) -> list[str]:
        return normalize_labels(v)

    @field_validator("group_ids", mode="before")
    @classmethod
    def _group_ids(cls, v: Any) -> list[str]:
        return list(dict.fromkeys(str(g) for g in (v or []) if str(g).strip()))

    @field_validator("first_met_at", mode="before")
    @classmethod
    def _first_met(cls, v: Any) -> Optional[str]:
        return check_iso_date(v, "first_met_at")

    @field_validator("keep_in_touch", "social", mode="before")
    @classmethod
    def _none_to_default(cls, v: Any) -> Any:
        return {} if v is None else v

    @field_validator("template_id", mode="before")
    @classmethod
    def empty_template_is_none(cls, v: Any) -> Optional[str]:
        return v or None

    @field_validator("phones")
    @classmethod
    def _unique_phones(cls, v: list[Phone]) -> list[Phone]:
        return dedupe_phones(v)

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
    # "" — снять шаблон (None означает «не менять»)
    template_id: Optional[str] = None
    fields: Optional[dict[str, Any]] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[list[str]] = None
    group_ids: Optional[list[str]] = None
    keep_in_touch: Optional[KeepInTouch] = None
    # Явный null у first_met_at / location / importance / closeness очищает поле
    # (см. repositories.contacts.NULLABLE_FIELDS)
    first_met_at: Optional[str] = None
    first_met_note: Optional[str] = Field(default=None, max_length=1000)
    address: Optional[str] = Field(default=None, max_length=500)
    location: Optional[Location] = None
    social: Optional[Social] = None
    importance: Optional[int] = Field(default=None, ge=1, le=5)
    closeness: Optional[int] = Field(default=None, ge=1, le=5)
    life_areas: Optional[list[str]] = None

    @field_validator("tags", "life_areas", mode="before")
    @classmethod
    def _labels(cls, v: Any) -> Optional[list[str]]:
        return None if v is None else normalize_labels(v)

    @field_validator("group_ids", mode="before")
    @classmethod
    def _group_ids(cls, v: Any) -> Optional[list[str]]:
        return None if v is None else list(dict.fromkeys(str(g) for g in v if str(g).strip()))

    @field_validator("first_met_at", mode="before")
    @classmethod
    def _first_met(cls, v: Any) -> Optional[str]:
        return check_iso_date(v, "first_met_at")

    @field_validator("phones")
    @classmethod
    def _unique_phones(cls, v: Optional[list[Phone]]) -> Optional[list[Phone]]:
        return dedupe_phones(v) if v is not None else None

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
    # Максимум из взаимодействий и прошедших событий календаря; клиенты его не пишут
    last_interaction_at: Optional[datetime] = None
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
        for ts_field in ("created_at", "updated_at", "last_synced_at", "last_interaction_at"):
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
