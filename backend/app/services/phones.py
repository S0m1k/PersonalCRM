"""
Телефоны: один номер — один ключ, как бы его ни записали.

89215535333, +7 921 553-53-33, 8 (921) 553-53-33 и 9215535333 → +79215535333 (E.164).
Разбор — библиотека phonenumbers (порт Google libphonenumber); номер без кода страны
считается номером из DEFAULT_PHONE_REGION (по умолчанию RU).

Ключ хранится рядом с номером (Phone.normalized) и используется для поиска, дублей,
календаря и ИИ. Сам номер (Phone.value) остаётся как введён — его видят пользователь,
телефон и Outlook / Google, массово переписывать формат там незачем.
"""

from __future__ import annotations

import re

import phonenumbers

from ..config import settings

# Короче этого «номер» из вопроса или поиска не считаем телефоном (год, сумма и т.п.)
MIN_SEARCH_DIGITS = 5
# Кусок номера в свободном тексте — от 7 цифр (553-53-33)
MIN_TEXT_DIGITS = 7
# Номер в свободном тексте: цифры с пробелами, скобками, дефисами, необязательный + в начале
_PHONE_IN_TEXT = re.compile(r"(?<![\w+])\+?\d[\d\s().\-]{5,}\d")


def digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


def phone_key(value: str) -> str:
    """
    Ключ номера: E.164 (+79215535333), если номер настоящий, иначе — только цифры
    (короткие и служебные номера, обрывки). Пусто — если цифр нет.
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parsed = phonenumbers.parse(raw, settings.default_phone_region)
    except phonenumbers.NumberParseException:
        return digits(raw)
    if phonenumbers.is_valid_number(parsed):
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    return digits(raw)


def same_phone(a: str, b: str) -> bool:
    key_a = phone_key(a)
    return bool(key_a) and key_a == phone_key(b)


def search_pattern(query: str) -> str | None:
    """
    Регэксп по Phone.normalized для поиска номером: полный номер — точное совпадение
    ключа, кусок номера (≥5 цифр) — подстрока. None — запрос не похож на номер.
    """
    found = digits(query)
    if len(found) < MIN_SEARCH_DIGITS or len(found) < len(query.strip()) * 0.5:
        return None
    key = phone_key(query)
    if key.startswith("+"):
        return f"^{re.escape(key)}$"
    return re.escape(found)


def find_in_text(text: str) -> list[str]:
    """
    Номера телефонов в свободном тексте (вопрос к ИИ): ключи без повторов.
    Берём настоящие номера и записи «как у телефона» (дефисы, скобки) от 7 цифр —
    «1 500 000 руб» или «в 2024 году» номерами не считаются.
    """
    keys = []
    for match in _PHONE_IN_TEXT.finditer(text):
        raw = match.group(0)
        key = phone_key(raw)
        looks_like_phone = any(c in raw for c in "-()") and len(digits(raw)) >= MIN_TEXT_DIGITS
        if key.startswith("+") or looks_like_phone:
            keys.append(key)
    return list(dict.fromkeys(keys))


def remove_from_text(text: str) -> str:
    """Текст без номеров телефонов (для разбора слов вокруг них)."""
    return _PHONE_IN_TEXT.sub(" ", text)
