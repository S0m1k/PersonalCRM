"""
Pydantic-модели пользователей.

Данные каждого пользователя лежат в отдельной базе MongoDB (db_name), поэтому
в контактах, шаблонах и т.п. поля владельца нет — изоляция на уровне базы.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Без внешней зависимости email-validator: достаточно «что-то@домен.зона»
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128
# bcrypt учитывает только первые 72 байта — длиннее молча обрезал бы, поэтому не принимаем
PASSWORD_MAX_BYTES = 72


def normalize_login(value: Any) -> Any:
    """Логин (email) сравниваем без учёта регистра и пробелов по краям."""
    return value.strip().lower() if isinstance(value, str) else value


def check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > PASSWORD_MAX_BYTES:
        raise ValueError(f"Пароль длиннее {PASSWORD_MAX_BYTES} байт (кириллица — 2 байта на букву)")
    return value


class UserCreate(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)
    name: str = Field(default="", max_length=100)

    _email = field_validator("email", mode="before")(normalize_login)
    _password = field_validator("password")(check_password_bytes)

    @field_validator("email")
    @classmethod
    def _check_email(cls, value: str) -> str:
        if not EMAIL_RE.match(value):
            raise ValueError("Некорректный email")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=PASSWORD_MAX)
    new_password: str = Field(..., min_length=PASSWORD_MIN, max_length=PASSWORD_MAX)

    _new_password = field_validator("new_password")(check_password_bytes)


class User(BaseModel):
    """Пользователь внутри приложения (без хешей — их отдаёт только репозиторий)."""

    id: str
    email: str
    name: str = ""
    db_name: str
    is_admin: bool = False
    has_carddav_password: bool = False
    # Растёт при смене пароля: токены со старой версией отклоняются
    token_version: int = 0
    created_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "User":
        created = doc.get("created_at") or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return cls(
            id=str(doc["_id"]),
            email=doc["email"],
            name=doc.get("name", ""),
            db_name=doc["db_name"],
            is_admin=doc.get("is_admin", False),
            has_carddav_password=bool(doc.get("carddav_secret")),
            token_version=doc.get("token_version", 0),
            created_at=created,
        )


class UserOut(BaseModel):
    """Ответ API о текущем пользователе."""

    id: str
    email: str
    name: str = ""
    # username — для совместимости со старым фронтендом (/api/auth/me)
    username: str
    has_carddav_password: bool = False

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            username=user.email,
            has_carddav_password=user.has_carddav_password,
        )
