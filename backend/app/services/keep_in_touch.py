"""
Keep in touch: кому пора написать.

У контакта задана частота (keep_in_touch.frequency_days). Срок = дата последнего взаимодействия
(нет взаимодействий — дата создания контакта) + частота. Корзины:
  overdue   — срок прошёл (по убыванию просрочки)
  due_soon  — срок сегодня или в ближайшие 7 дней
  upcoming  — позже
  snoozed   — напоминание отложено до даты (включительно), в какой бы корзине ни был срок
Чистая логика без IO — собирает данные репозиторий (repositories/keep_in_touch.py).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

from pydantic import BaseModel, Field

DUE_SOON_DAYS = 7


class KeepInTouchItem(BaseModel):
    contact_id: str
    name: str
    company: str = ""
    tags: list[str] = Field(default_factory=list)
    importance: Optional[int] = None
    frequency_days: int
    due_date: date
    # Сколько дней просрочено (0, если срок не прошёл) и сколько осталось (0, если прошёл)
    days_overdue: int = 0
    days_until: int = 0
    last_interaction_at: Optional[datetime] = None
    snoozed_until: Optional[date] = None


class KeepInTouchUnsetItem(BaseModel):
    """Контакт без частоты (колонка «Без частоты» на доске)."""

    contact_id: str
    name: str
    company: str = ""
    tags: list[str] = Field(default_factory=list)
    importance: Optional[int] = None
    last_interaction_at: Optional[datetime] = None


class KeepInTouchBuckets(BaseModel):
    overdue: list[KeepInTouchItem] = Field(default_factory=list)
    due_soon: list[KeepInTouchItem] = Field(default_factory=list)
    upcoming: list[KeepInTouchItem] = Field(default_factory=list)
    snoozed: list[KeepInTouchItem] = Field(default_factory=list)
    # Только при include_unset=true; иначе поля нет в ответе
    unset: Optional[list[KeepInTouchUnsetItem]] = None


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _as_date(value: object) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _name(doc: dict) -> str:
    return " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip() or "Без имени"


def build_item(doc: dict, last: Optional[datetime], today: date) -> Optional[KeepInTouchItem]:
    """Строка для контакта с частотой; None — частота не задана."""
    kit = doc.get("keep_in_touch") or {}
    frequency = kit.get("frequency_days")
    if not frequency:
        return None
    last = _aware(last) if last else None
    anchor_raw = last or doc.get("created_at")
    anchor = _aware(anchor_raw).date() if isinstance(anchor_raw, datetime) else today
    due = anchor + timedelta(days=int(frequency))
    delta = (today - due).days
    return KeepInTouchItem(
        contact_id=str(doc["_id"]),
        name=_name(doc),
        company=doc.get("company", ""),
        tags=list(doc.get("tags") or []),
        importance=doc.get("importance"),
        frequency_days=int(frequency),
        due_date=due,
        days_overdue=max(delta, 0),
        days_until=max(-delta, 0),
        last_interaction_at=last,
        snoozed_until=_as_date(kit.get("snoozed_until")),
    )


def bucketize(
    docs: Iterable[dict], last_by_contact: dict[str, datetime], today: date
) -> KeepInTouchBuckets:
    buckets = KeepInTouchBuckets()
    for doc in docs:
        item = build_item(doc, last_by_contact.get(str(doc["_id"])) or doc.get("last_interaction_at"), today)
        if item is None:
            continue
        if item.snoozed_until is not None and item.snoozed_until >= today:
            buckets.snoozed.append(item)
        elif item.days_overdue > 0:
            buckets.overdue.append(item)
        elif item.days_until <= DUE_SOON_DAYS:
            buckets.due_soon.append(item)
        else:
            buckets.upcoming.append(item)
    buckets.overdue.sort(key=lambda i: (-i.days_overdue, -(i.importance or 0), i.name))
    for bucket in (buckets.due_soon, buckets.upcoming, buckets.snoozed):
        bucket.sort(key=lambda i: (i.due_date, i.name))
    return buckets


def build_unset_item(doc: dict, last: Optional[datetime]) -> KeepInTouchUnsetItem:
    last = last or doc.get("last_interaction_at")
    return KeepInTouchUnsetItem(
        contact_id=str(doc["_id"]),
        name=_name(doc),
        company=doc.get("company", ""),
        tags=list(doc.get("tags") or []),
        importance=doc.get("importance"),
        last_interaction_at=_aware(last) if last else None,
    )
