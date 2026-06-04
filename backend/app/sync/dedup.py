"""
Движок дедупликации контактов.

Алгоритм:
  1. Точное совпадение нормализованного телефона → score += 100
  2. Точное совпадение email (lowercase) → score += 90
  3. Fuzzy-match по имени (SequenceMatcher):
       ratio > 0.85 → score += 70
       ratio > 0.60 → score += 30
  4. Та же компания (непустая) → score += 20

Итог:
  score ≥ 90 → "auto_merge"   (выполняется без вопросов)
  score 70–89 → "suggest_merge" (показываем UI side-by-side)
  score < 70  → "new"          (создаём отдельный контакт)

Все функции — чистые (без IO), легко тестируются.
"""

from __future__ import annotations

from difflib import SequenceMatcher


# ---------------------------------------------------------------------------
# Нормализация телефона
# ---------------------------------------------------------------------------


def normalize_phone(phone: str) -> str:
    """
    Нормализовать номер телефона для сравнения.

    Оставляем только цифры. Российские номера вида 8XXXXXXXXXX → 7XXXXXXXXXX.
    Пример: "+7 (900) 123-45-67" → "79001234567"
             "8-900-123-45-67"   → "79001234567"
    """
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


# ---------------------------------------------------------------------------
# Поиск дублей
# ---------------------------------------------------------------------------


def find_duplicates(
    new_contact: dict,
    existing_contacts: list[dict],
) -> list[dict]:
    """
    Найти потенциальные дубликаты нового контакта в существующей базе.

    Возвращает список dict (отсортированных по убыванию score):
    {
        "existing_contact": dict,
        "score": int,          # 0–100
        "reasons": list[str],  # объяснение совпадения
        "action": str,         # "auto_merge" | "suggest_merge" | "new"
    }
    """
    matches = []

    new_phones = {
        normalize_phone(p["value"])
        for p in new_contact.get("phones", [])
        if p.get("value")
    }
    new_emails = {
        e["value"].strip().lower()
        for e in new_contact.get("emails", [])
        if e.get("value")
    }
    new_name = (
        f"{new_contact.get('first_name', '')} {new_contact.get('last_name', '')}"
        .strip()
        .lower()
    )
    new_company = (new_contact.get("company") or "").strip().lower()

    for existing in existing_contacts:
        score = 0
        reasons: list[str] = []

        # 1. Телефон (самый надёжный сигнал)
        if new_phones:
            existing_phones = {
                normalize_phone(p["value"])
                for p in existing.get("phones", [])
                if p.get("value")
            }
            if new_phones & existing_phones:
                score += 100
                reasons.append("совпадение телефона")

        # 2. Email
        if new_emails:
            existing_emails = {
                e["value"].strip().lower()
                for e in existing.get("emails", [])
                if e.get("value")
            }
            if new_emails & existing_emails:
                score += 90
                reasons.append("совпадение email")

        # 3. Fuzzy-match по имени
        existing_name = (
            f"{existing.get('first_name', '')} {existing.get('last_name', '')}"
            .strip()
            .lower()
        )
        if new_name and existing_name:
            ratio = SequenceMatcher(None, new_name, existing_name).ratio()
            if ratio > 0.85:
                score += 70
                reasons.append(f"похожее имя ({ratio:.0%})")
            elif ratio > 0.60:
                score += 30
                reasons.append(f"возможно похожее имя ({ratio:.0%})")

        # 4. Та же компания (усиливающий сигнал)
        existing_company = (existing.get("company") or "").strip().lower()
        if new_company and new_company == existing_company:
            score += 20
            reasons.append("та же компания")

        if score >= 70:
            matches.append(
                {
                    "existing_contact": existing,
                    "score": min(score, 100),
                    "reasons": reasons,
                    "action": "auto_merge" if score >= 90 else "suggest_merge",
                }
            )

    return sorted(matches, key=lambda x: x["score"], reverse=True)


# ---------------------------------------------------------------------------
# Merge контактов
# ---------------------------------------------------------------------------


def merge_contacts(primary: dict, secondary: dict) -> dict:
    """
    Слить два контакта. primary — основной (сохраняет свои данные),
    secondary — дополняющий (заполняет пустые поля, добавляет недостающие телефоны/email).

    Возвращает новый dict (не мутирует входные данные).
    """
    merged = {**primary}
    # Копируем вложенные списки, чтобы не мутировать входной primary
    # ({**primary} — поверхностная копия, списки остаются общими).
    merged["phones"] = list(merged.get("phones") or [])
    merged["emails"] = list(merged.get("emails") or [])

    # Телефоны: добавить уникальные из secondary
    existing_phones = {
        normalize_phone(p["value"])
        for p in merged["phones"]
        if p.get("value")
    }
    for phone in secondary.get("phones", []):
        if phone.get("value") and normalize_phone(phone["value"]) not in existing_phones:
            merged["phones"].append(phone)
            existing_phones.add(normalize_phone(phone["value"]))

    # Email: добавить уникальные
    existing_emails = {
        e["value"].strip().lower()
        for e in merged["emails"]
        if e.get("value")
    }
    for email in secondary.get("emails", []):
        if email.get("value") and email["value"].strip().lower() not in existing_emails:
            merged["emails"].append(email)
            existing_emails.add(email["value"].strip().lower())

    # Заполнить пустые скалярные поля из secondary
    for field in ("company", "position", "city", "birthday", "notes"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]

    # external_ids: объединить. primary имеет приоритет, НО только своими
    # непустыми значениями — иначе primary с {google: None} затёр бы реальный
    # google-ID из secondary.
    merged_ext = dict(secondary.get("external_ids") or {})
    for key, val in (merged.get("external_ids") or {}).items():
        if val is not None:
            merged_ext[key] = val
    merged["external_ids"] = merged_ext

    # sources: объединить уникальные
    primary_sources: list[str] = list(merged.get("sources") or [])
    if merged.get("source") and merged["source"] not in primary_sources:
        primary_sources.append(merged["source"])
    for src in list(secondary.get("sources") or []):
        if src not in primary_sources:
            primary_sources.append(src)
    if secondary.get("source") and secondary["source"] not in primary_sources:
        primary_sources.append(secondary["source"])
    merged["sources"] = primary_sources

    return merged
