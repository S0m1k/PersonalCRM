"""
Инсайты сети: распределения контактов (компании, города, теги, группы, частота общения,
давность последнего взаимодействия, прирост по месяцам). Чистая логика без IO.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel

MIN_FOR_INSIGHTS = 20
TOP_N = 10
GROWTH_MONTHS = 24

RECENCY_BUCKETS = (
    ("Меньше месяца", 30),
    ("1–3 месяца", 90),
    ("3–6 месяцев", 180),
    ("6–12 месяцев", 365),
    ("Больше года", None),
)
NEVER = "Никогда"
FREQUENCY_BUCKETS = (
    ("Раз в неделю и чаще", 7),
    ("Раз в месяц", 31),
    ("Раз в квартал", 92),
    ("Раз в полгода", 183),
    ("Раз в год", 365),
    ("Реже раза в год", None),
)
NO_FREQUENCY = "Не задана"


class Slice(BaseModel):
    label: str
    count: int


class MonthPoint(BaseModel):
    month: str  # YYYY-MM
    added: int
    total: int


class Insights(BaseModel):
    total: int
    # False — контактов меньше MIN_FOR_INSIGHTS: данные есть, но выводы ещё шаткие
    enough: bool
    required: int = MIN_FOR_INSIGHTS
    by_company: list[Slice]
    by_city: list[Slice]
    by_tag: list[Slice]
    by_group: list[Slice]
    by_frequency: list[Slice]
    by_recency: list[Slice]
    growth: list[MonthPoint]


def _aware(value: object) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _top(counter: Counter, limit: int = TOP_N) -> list[Slice]:
    ranked = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:limit]
    return [Slice(label=label, count=count) for label, count in ranked]


def _clean(value: object) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _count_values(docs: list[dict], field: str) -> Counter:
    counter: Counter = Counter()
    canonical: dict[str, str] = {}
    for doc in docs:
        value = _clean(doc.get(field))
        if value:
            counter[canonical.setdefault(value.lower(), value)] += 1
    return counter


def _count_tags(docs: list[dict]) -> Counter:
    counter: Counter = Counter()
    canonical: dict[str, str] = {}
    for doc in docs:
        # В одной карточке «друг» и «Друг» — один тег; подпись берём первую встреченную
        seen = {t.strip().lower(): t.strip() for t in reversed(doc.get("tags") or []) if isinstance(t, str) and t.strip()}
        for key, tag in seen.items():
            counter[canonical.setdefault(key, tag)] += 1
    return counter


def _bucketed(buckets: tuple, days: Optional[float]) -> Optional[str]:
    if days is None:
        return None
    for label, limit in buckets:
        if limit is None or days <= limit:
            return label
    return buckets[-1][0]


def recency_series(docs: list[dict], now: datetime) -> list[Slice]:
    counts = Counter()
    for doc in docs:
        last = _aware(doc.get("last_interaction_at"))
        label = _bucketed(RECENCY_BUCKETS, max(0.0, (now - last).total_seconds() / 86_400)) if last else NEVER
        counts[label] += 1
    order = [label for label, _ in RECENCY_BUCKETS] + [NEVER]
    return [Slice(label=label, count=counts[label]) for label in order]


def frequency_series(docs: list[dict]) -> list[Slice]:
    counts = Counter()
    for doc in docs:
        days = (doc.get("keep_in_touch") or {}).get("frequency_days")
        counts[_bucketed(FREQUENCY_BUCKETS, days) or NO_FREQUENCY] += 1
    order = [label for label, _ in FREQUENCY_BUCKETS] + [NO_FREQUENCY]
    return [Slice(label=label, count=counts[label]) for label in order]


def growth_series(docs: list[dict], now: datetime, months: int = GROWTH_MONTHS) -> list[MonthPoint]:
    per_month: Counter = Counter()
    for doc in docs:
        created = _aware(doc.get("created_at"))
        if created:
            per_month[f"{created.year:04d}-{created.month:02d}"] += 1
    if not per_month:
        return []
    first = min(per_month)
    cursor_year, cursor_month = int(first[:4]), int(first[5:])
    points: list[MonthPoint] = []
    total = 0
    while (cursor_year, cursor_month) <= (now.year, now.month):
        key = f"{cursor_year:04d}-{cursor_month:02d}"
        total += per_month[key]
        points.append(MonthPoint(month=key, added=per_month[key], total=total))
        cursor_year, cursor_month = (cursor_year + 1, 1) if cursor_month == 12 else (cursor_year, cursor_month + 1)
    return points[-months:]


def build_insights(docs: list[dict], group_names: dict[str, str], now: Optional[datetime] = None) -> Insights:
    now = now or datetime.now(timezone.utc)
    by_group: Counter = Counter()
    for doc in docs:
        for group_id in set(doc.get("group_ids") or []):
            if group_id in group_names:
                by_group[group_names[group_id]] += 1
    return Insights(
        total=len(docs),
        enough=len(docs) >= MIN_FOR_INSIGHTS,
        by_company=_top(_count_values(docs, "company")),
        by_city=_top(_count_values(docs, "city")),
        by_tag=_top(_count_tags(docs)),
        by_group=_top(by_group),
        by_frequency=frequency_series(docs),
        by_recency=recency_series(docs, now),
        growth=growth_series(docs, now),
    )
