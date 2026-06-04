"""
Парсеры файлов для импорта контактов.

Поддерживаемые форматы:
  - vCard (.vcf)          — parse_vcard
  - CSV Google-формат     — parse_csv
  - Telegram export JSON  — parse_telegram_export
  - detect_format         — автоопределение по расширению/содержимому

Все функции возвращают list[dict], совместимый с ContactCreate.model_validate().
Функции чистые (без IO) — легко тестируются.
"""

from __future__ import annotations

import csv
import json
import re
from io import StringIO


# ---------------------------------------------------------------------------
# vCard парсер
# ---------------------------------------------------------------------------


def parse_vcard(content: str) -> list[dict]:
    """
    Парсинг vCard / .vcf формата (vCard 2.1 и 3.0).

    Обрабатывает:
      - FN (full name) → first_name + last_name
      - N (structured name) → first_name + last_name (если FN отсутствует)
      - TEL → phones
      - EMAIL → emails
      - ORG → company
      - TITLE → position
      - BDAY → birthday (YYYY-MM-DD или YYYYMMDD)
      - NOTE → notes
    """
    contacts: list[dict] = []
    current: dict = {}
    in_vcard = False

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if line.upper() == "BEGIN:VCARD":
            current = {}
            in_vcard = True
            continue

        if line.upper() == "END:VCARD":
            in_vcard = False
            if current and (current.get("first_name") or current.get("last_name")):
                _finalize_contact(current)
                contacts.append(current)
            current = {}
            continue

        if not in_vcard or ":" not in line:
            continue

        key_part, _, value = line.partition(":")
        key_base = key_part.split(";")[0].upper()
        value = value.strip()

        if key_base == "FN":
            # Full Name → разбиваем на имя + фамилия по первому пробелу
            parts = value.split(" ", 1)
            current["first_name"] = parts[0]
            current["last_name"] = parts[1] if len(parts) > 1 else ""

        elif key_base == "N" and "first_name" not in current:
            # N:Фамилия;Имя;Отчество;Префикс;Суффикс
            n_parts = value.split(";")
            current["last_name"] = n_parts[0].strip() if len(n_parts) > 0 else ""
            current["first_name"] = n_parts[1].strip() if len(n_parts) > 1 else ""

        elif key_base == "TEL":
            label = _extract_tel_label(key_part)
            current.setdefault("phones", []).append({"value": value, "label": label})

        elif key_base == "EMAIL":
            current.setdefault("emails", []).append({"value": value, "label": "email"})

        elif key_base == "ORG":
            # ORG может быть "Компания;Отдел" — берём первую часть
            current["company"] = value.split(";")[0].strip()

        elif key_base == "TITLE":
            current["position"] = value

        elif key_base == "BDAY":
            current["birthday"] = _parse_vcard_date(value)

        elif key_base == "NOTE":
            current["notes"] = value

    return contacts


def _extract_tel_label(key_part: str) -> str:
    """Извлечь метку телефона из параметров TYPE=CELL,WORK и т.п."""
    upper = key_part.upper()
    if "CELL" in upper or "MOBILE" in upper:
        return "мобильный"
    if "WORK" in upper:
        return "рабочий"
    if "HOME" in upper:
        return "домашний"
    return "телефон"


def _parse_vcard_date(value: str) -> str | None:
    """Нормализовать дату из vCard в YYYY-MM-DD или None."""
    # Убираем возможный префикс "--" (vCard 3.0 без года)
    value = value.lstrip("-")
    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) == 8:
        # YYYYMMDD
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    if len(digits) >= 6:
        # YYYYMMDD с возможными разделителями
        try:
            return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
        except Exception:
            pass
    return None


def _finalize_contact(c: dict) -> None:
    """Заполнить обязательные поля дефолтами."""
    c.setdefault("phones", [])
    c.setdefault("emails", [])
    c.setdefault("company", "")
    c.setdefault("position", "")
    c.setdefault("birthday", None)
    c.setdefault("notes", "")
    c["source"] = "vcard"
    c["sources"] = ["vcard"]
    c.setdefault("external_ids", {"outlook": None, "google": None, "telegram": None})
    c.setdefault("category", "")
    c.setdefault("priority", "")
    c.setdefault("custom_fields", [])
    c.setdefault("relationships", [])


# ---------------------------------------------------------------------------
# CSV парсер (Google Contacts export + общий формат)
# ---------------------------------------------------------------------------


def parse_csv(content: str) -> list[dict]:
    """
    Парсинг CSV (Google Contacts export и общий формат).

    Поддерживает как русские заголовки (Имя, Фамилия),
    так и Google-export заголовки (Given Name, First Name, Family Name, Last Name).
    """
    reader = csv.DictReader(StringIO(content))
    contacts: list[dict] = []

    for row in reader:
        first_name = (
            row.get("Given Name")
            or row.get("First Name")
            or row.get("Имя")
            or ""
        ).strip()
        last_name = (
            row.get("Family Name")
            or row.get("Last Name")
            or row.get("Фамилия")
            or ""
        ).strip()

        if not first_name and not last_name:
            # Пропускаем строки без имени
            continue

        contact: dict = {
            "first_name": first_name,
            "last_name": last_name,
            "phones": [],
            "emails": [],
            "company": (
                row.get("Organization 1 - Name")
                or row.get("Company")
                or row.get("Компания")
                or ""
            ).strip(),
            "position": (
                row.get("Organization 1 - Title")
                or row.get("Job Title")
                or row.get("Должность")
                or ""
            ).strip(),
            "notes": (row.get("Notes") or row.get("Заметки") or "").strip(),
            "birthday": None,
            "source": "csv",
            "sources": ["csv"],
            "external_ids": {"outlook": None, "google": None, "telegram": None},
            "category": "",
            "priority": "",
            "custom_fields": [],
            "relationships": [],
        }

        # Телефоны: Google export нумерует поля Phone 1 - Value, Phone 2 - Value, …
        for i in range(1, 6):
            key = f"Phone {i} - Value"
            if row.get(key):
                label_key = f"Phone {i} - Type"
                contact["phones"].append({
                    "value": row[key].strip(),
                    "label": row.get(label_key, "телефон").strip() or "телефон",
                })

        # Телефоны: альтернативные заголовки
        for key in ("Mobile Phone", "Primary Phone", "Телефон"):
            if row.get(key) and not contact["phones"]:
                contact["phones"].append({"value": row[key].strip(), "label": "телефон"})

        # Email: Google export нумерует поля E-mail 1 - Value, …
        for i in range(1, 6):
            key = f"E-mail {i} - Value"
            if row.get(key):
                label_key = f"E-mail {i} - Type"
                contact["emails"].append({
                    "value": row[key].strip(),
                    "label": row.get(label_key, "email").strip() or "email",
                })

        # Email: альтернативные заголовки
        for key in ("E-mail Address", "Email", "Email Address", "Email 1 - Value", "Email адрес"):
            if row.get(key) and not contact["emails"]:
                contact["emails"].append({"value": row[key].strip(), "label": "email"})

        # Дата рождения
        bday_raw = (
            row.get("Birthday")
            or row.get("Event 1 - Value")  # Google Sometimes stores BDAY here
            or row.get("Дата рождения")
            or ""
        ).strip()
        if bday_raw:
            contact["birthday"] = _normalize_csv_date(bday_raw)

        contacts.append(contact)

    return contacts


def _normalize_csv_date(value: str) -> str | None:
    """Попытаться нормализовать дату в YYYY-MM-DD."""
    value = value.strip()
    # Уже в нужном формате
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    # DD.MM.YYYY
    m = re.match(r"^(\d{2})\.(\d{2})\.(\d{4})$", value)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # M/D/YYYY or MM/DD/YYYY
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if m:
        return f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
    return None


# ---------------------------------------------------------------------------
# Telegram export JSON парсер
# ---------------------------------------------------------------------------


def parse_telegram_export(content: str) -> list[dict]:
    """
    Парсинг Telegram Desktop contacts export (JSON).

    Telegram Desktop экспортирует два варианта:
    1. Список: [{first_name, last_name, phone_number, date}, ...]
    2. Вложенный: {"contacts": {"list": [...]}}

    Возвращает список контактов в формате CRM.
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Невалидный JSON Telegram-экспорта: {exc}") from exc

    # Определяем, где лежит список контактов
    if isinstance(data, list):
        contacts_list = data
    elif isinstance(data, dict):
        contacts_list = (
            data.get("contacts", {}).get("list", [])
            or data.get("list", [])
            or []
        )
    else:
        contacts_list = []

    contacts: list[dict] = []

    for tc in contacts_list:
        if not isinstance(tc, dict):
            continue

        first_name = (tc.get("first_name") or "").strip()
        last_name = (tc.get("last_name") or "").strip()

        if not first_name and not last_name:
            continue

        contact: dict = {
            "first_name": first_name,
            "last_name": last_name,
            "phones": [],
            "emails": [],
            "company": "",
            "position": "",
            "birthday": None,
            "notes": "",
            "source": "telegram",
            "sources": ["telegram"],
            "external_ids": {"outlook": None, "google": None, "telegram": None},
            "category": "",
            "priority": "",
            "custom_fields": [],
            "relationships": [],
        }

        phone = (tc.get("phone_number") or tc.get("phone") or "").strip()
        if phone:
            contact["phones"].append({"value": phone, "label": "telegram"})

        contacts.append(contact)

    return contacts


# ---------------------------------------------------------------------------
# Автоопределение формата
# ---------------------------------------------------------------------------


def detect_format(filename: str, content: str) -> str:
    """
    Определить формат файла.

    Возвращает: "vcard" | "csv" | "telegram" | "unknown"
    """
    name_lower = filename.lower()
    if name_lower.endswith(".vcf"):
        return "vcard"
    if name_lower.endswith(".csv"):
        return "csv"
    if name_lower.endswith(".json"):
        # Проверяем, похоже ли на Telegram-экспорт
        try:
            data = json.loads(content[:2000])  # первые 2000 байт достаточно
            if isinstance(data, list) and data and isinstance(data[0], dict):
                if "first_name" in data[0] or "phone_number" in data[0]:
                    return "telegram"
            if isinstance(data, dict) and "contacts" in data:
                return "telegram"
        except Exception:
            pass
        return "unknown"
    # По содержимому
    stripped = content.lstrip()
    if stripped.upper().startswith("BEGIN:VCARD"):
        return "vcard"
    return "unknown"
