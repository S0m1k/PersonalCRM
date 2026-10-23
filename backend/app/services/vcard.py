"""
vCard 3.0 для CardDAV (RFC 2426 / RFC 6350): контакт CRM ↔ карточка телефона.

Чтение понимает то, что присылают iPhone и Android (DAVx⁵): перенос длинных строк,
экранирование, группы вида `item1.EMAIL`, параметры `type=CELL;type=pref` и `TYPE=CELL,VOICE`.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from ..models.contact import ContactOut

MAX_LINE_OCTETS = 75
# День рождения без года: так же хранят Outlook и Apple
NO_YEAR = "1604"

_PHONE_TYPES = {"мобильный": "CELL", "рабочий": "WORK", "домашний": "HOME"}
_PHONE_LABELS = (("CELL", "мобильный"), ("IPHONE", "мобильный"), ("WORK", "рабочий"), ("HOME", "домашний"))
_EMAIL_TYPES = {"рабочий": "WORK", "личный": "HOME", "домашний": "HOME"}
_EMAIL_LABELS = (("WORK", "рабочий"), ("HOME", "личный"))


# ---------------------------------------------------------------------------
# Экранирование и перенос строк
# ---------------------------------------------------------------------------


def _escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")
    )


def _unescape(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def _split_unescaped(value: str, sep: str) -> list[str]:
    """Разбить по разделителю, не задевая экранированные `\\;`."""
    return re.split(rf"(?<!\\){re.escape(sep)}", value)


def _fold(line: str) -> str:
    """Перенос по 75 байт UTF-8, не разрывая символы; продолжение начинается с пробела."""
    chunks: list[str] = []
    current, size, limit = "", 0, MAX_LINE_OCTETS
    for ch in line:
        width = len(ch.encode())
        if size + width > limit:
            chunks.append(current)
            current, size, limit = "", 0, MAX_LINE_OCTETS - 1
        current += ch
        size += width
    chunks.append(current)
    return "\r\n ".join(chunks)


def _unfold(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [line for line in re.sub(r"\n[ \t]", "", text).split("\n") if line.strip()]


# ---------------------------------------------------------------------------
# Запись
# ---------------------------------------------------------------------------


def contact_to_vcard(contact: ContactOut, uid: Optional[str] = None) -> str:
    """Карточка vCard 3.0 со строками через CRLF."""
    full_name = " ".join(p for p in (contact.first_name, contact.last_name) if p) or "Без имени"
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "PRODID:-//PersonalCRM//CardDAV//RU",
        f"UID:{uid or contact.id}",
        f"N:{_escape(contact.last_name)};{_escape(contact.first_name)};;;",
        f"FN:{_escape(full_name)}",
    ]
    if contact.company:
        lines.append(f"ORG:{_escape(contact.company)}")
    if contact.position:
        lines.append(f"TITLE:{_escape(contact.position)}")
    for phone in contact.phones:
        lines.append(f"TEL;TYPE={_PHONE_TYPES.get(phone.label, 'VOICE')}:{_escape(phone.value)}")
    for email in contact.emails:
        kind = _EMAIL_TYPES.get(email.label)
        lines.append(f"EMAIL;TYPE=INTERNET{',' + kind if kind else ''}:{_escape(email.value)}")
    if contact.city:
        lines.append(f"ADR;TYPE=HOME:;;;{_escape(contact.city)};;;")
    if contact.birthday:
        birthday = contact.birthday
        lines.append(f"BDAY:--{birthday[5:]}" if birthday.startswith(NO_YEAR) else f"BDAY:{birthday}")
    if contact.notes:
        lines.append(f"NOTE:{_escape(contact.notes)}")
    if contact.category:
        lines.append(f"CATEGORIES:{_escape(contact.category)}")
    lines.append(f"REV:{contact.updated_at.strftime('%Y%m%dT%H%M%SZ')}")
    lines.append("END:VCARD")
    return "".join(_fold(line) + "\r\n" for line in lines)


# ---------------------------------------------------------------------------
# Чтение
# ---------------------------------------------------------------------------


def _parse_line(line: str) -> tuple[str, set[str], str]:
    """`item1.TEL;type=CELL;type=pref:+7…` → ("TEL", {"CELL", "PREF"}, "+7…")."""
    head, _, value = line.partition(":")
    name, *params = head.split(";")
    name = name.split(".")[-1].upper()
    types: set[str] = set()
    for param in params:
        key, has_value, raw = param.partition("=")
        if not has_value:
            types.add(key.upper())  # vCard 2.1: TEL;CELL:…
        elif key.upper() == "TYPE":
            types.update(t.strip().strip('"').upper() for t in raw.split(","))
    return name, types, value


def _label(types: set[str], mapping: Iterable[tuple[str, str]], default: str) -> str:
    return next((label for kind, label in mapping if kind in types), default)


def _parse_birthday(value: str) -> Optional[str]:
    digits = value.strip().replace("-", "")
    if value.startswith("--") and len(digits) == 4:
        return f"{NO_YEAR}-{digits[:2]}-{digits[2:]}"
    if len(digits) >= 8 and digits[:8].isdigit():
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    return None


def vcard_uid(text: str) -> Optional[str]:
    for line in _unfold(text):
        name, _, value = _parse_line(line)
        if name == "UID":
            return _unescape(value).strip() or None
    return None


def vcard_to_fields(text: str) -> dict:
    """
    Поля контакта из карточки. Отсутствующие в карточке поля возвращаются пустыми —
    чтобы удаление на телефоне (например, телефона) доходило до CRM.
    """
    fields: dict = {
        "first_name": "",
        "last_name": "",
        "company": "",
        "position": "",
        "city": "",
        "birthday": None,
        "notes": "",
        "category": "",
        "phones": [],
        "emails": [],
    }
    full_name = ""
    for line in _unfold(text):
        name, types, value = _parse_line(line)
        if name == "N":
            parts = [_unescape(p).strip() for p in _split_unescaped(value, ";")] + ["", ""]
            fields["last_name"], fields["first_name"] = parts[0], parts[1]
        elif name == "FN":
            full_name = _unescape(value).strip()
        elif name == "ORG":
            fields["company"] = _unescape(_split_unescaped(value, ";")[0]).strip()
        elif name == "TITLE":
            fields["position"] = _unescape(value).strip()
        elif name == "TEL" and value.strip():
            fields["phones"].append({"value": _unescape(value).strip(), "label": _label(types, _PHONE_LABELS, "телефон")})
        elif name == "EMAIL" and value.strip():
            fields["emails"].append({"value": _unescape(value).strip(), "label": _label(types, _EMAIL_LABELS, "email")})
        elif name == "ADR" and not fields["city"]:
            parts = _split_unescaped(value, ";")
            fields["city"] = _unescape(parts[3]).strip() if len(parts) > 3 else ""
        elif name == "BDAY":
            fields["birthday"] = _parse_birthday(value)
        elif name == "NOTE":
            fields["notes"] = _unescape(value)
        elif name == "CATEGORIES":
            fields["category"] = _unescape(value).strip()

    if not fields["first_name"] and not fields["last_name"] and full_name:
        first, _, last = full_name.partition(" ")
        fields["first_name"], fields["last_name"] = first, last
    return fields
