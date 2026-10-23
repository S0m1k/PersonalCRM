"""
Проверка и нормализация значений типизированных полей контакта по шаблону.

Чистые функции без доступа к БД: вход — описания полей и сырые значения,
выход — нормализованный dict или FieldValidationError со всеми ошибками сразу.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from ..models.template import FieldDef

MAX_TEXT = 500
MAX_LONGTEXT = 10_000

_TRUE = {"true", "1", "да", "yes", "on"}
_FALSE = {"false", "0", "нет", "no", "off"}
_URL = re.compile(r"^(https?://)?[^\s/$.?#][^\s]*\.[^\s]{2,}$", re.IGNORECASE)


class FieldValidationError(ValueError):
    """Одна или несколько ошибок в значениях полей."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def _text(limit: int) -> Callable[[Any], str]:
    def convert(value: Any) -> str:
        text = str(value).strip()
        if len(text) > limit:
            raise ValueError(f"не длиннее {limit} символов")
        return text

    return convert


def _date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValueError("дата в формате ГГГГ-ММ-ДД") from None


def _number(value: Any) -> int | float:
    if isinstance(value, bool):
        raise ValueError("нужно число")
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        raise ValueError("нужно число") from None
    return int(number) if number.is_integer() else number


def _url(value: Any) -> str:
    text = str(value).strip()
    if not _URL.match(text):
        raise ValueError("нужна ссылка, например example.com")
    return text if re.match(r"^https?://", text, re.IGNORECASE) else f"https://{text}"


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError("нужно да или нет")


_CONVERTERS: dict[str, Callable[[Any], Any]] = {
    "text": _text(MAX_TEXT),
    "longtext": _text(MAX_LONGTEXT),
    "date": _date,
    "number": _number,
    "url": _url,
    "bool": _bool,
}


def _convert(field: FieldDef, value: Any) -> Any:
    if field.type == "select":
        text = str(value).strip()
        if text not in field.options:
            raise ValueError(f"одно из: {', '.join(field.options)}")
        return text
    return _CONVERTERS[field.type](value)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_field_values(defs: list[FieldDef], values: dict[str, Any]) -> dict[str, Any]:
    """
    Вернуть новый dict с нормализованными значениями.

    Пустые значения отбрасываются. Ключи, которых нет в шаблоне, сохраняются как есть
    (поле удалили из шаблона — данные не теряем).
    """
    by_key = {d.key: d for d in defs}
    result: dict[str, Any] = {}
    errors: list[str] = []
    for key, value in values.items():
        if _is_empty(value):
            continue
        field = by_key.get(key)
        if field is None:
            result[key] = value
            continue
        try:
            result[key] = _convert(field, value)
        except ValueError as exc:
            errors.append(f"«{field.label}»: {exc}")
    if errors:
        raise FieldValidationError(errors)
    return result
