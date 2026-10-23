"""
Ближайшие дни рождения — чистая функция над списком {id, name, birthday}.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

# Outlook/Apple хранят день рождения без года как 1604 или 1900
MIN_KNOWN_YEAR = 1901


def _parse(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _in_year(born: date, year: int) -> date:
    """День рождения в указанном году; 29 февраля в невисокосный — 28-го."""
    try:
        return born.replace(year=year)
    except ValueError:
        return date(year, 2, 28)


def upcoming_birthdays(people: list[dict], today: date, days: int) -> list[dict]:
    """Дни рождения в ближайшие `days` дней (включая сегодня), по возрастанию даты."""
    result = []
    for person in people:
        born = _parse(person.get("birthday"))
        if born is None:
            continue
        next_date = _in_year(born, today.year)
        if next_date < today:
            next_date = _in_year(born, today.year + 1)
        days_until = (next_date - today).days
        if days_until > days:
            continue
        result.append(
            {
                "contact_id": person["id"],
                "name": person["name"],
                "date": next_date.isoformat(),
                "days_until": days_until,
                "turns": next_date.year - born.year if born.year >= MIN_KNOWN_YEAR else None,
            }
        )
    return sorted(result, key=lambda r: (r["days_until"], r["name"]))
