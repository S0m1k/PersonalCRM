"""
Чистая логика напоминаний: следующая дата повторения.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

WEEK_DAYS = 7


def _add_months(value: date, months: int) -> date:
    index = value.month - 1 + months
    year, month = value.year + index // 12, index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def next_due_date(current: date, repeat: str) -> date | None:
    """Следующая дата для повторяющегося напоминания; None для repeat=none."""
    if repeat == "weekly":
        return current + timedelta(days=WEEK_DAYS)
    if repeat == "monthly":
        return _add_months(current, 1)
    if repeat == "yearly":
        return _add_months(current, 12)
    return None
