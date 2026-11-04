"""
Аналитика по базе пользователя: агрегаты, ряды по времени, «давно не общались».

Чистые функции над базой одного пользователя (db передаётся явно), без модели. Каждый
инструмент описан в реестре ANALYTICS_TOOLS (имя, описание, JSON-схема параметров), параметры
проверяются validate_params, ошибки — ToolError. Тот же реестр понадобится MCP-серверу.

Результат инструмента — ToolOutput: facts (компактные данные для модели, чтобы написать вывод)
и blocks (готовые блоки графика/таблицы/контактов для интерфейса). Блоки строятся из данных базы,
а не из слов модели, поэтому числа на графиках всегда настоящие.

Коллекции interactions (взаимодействия {contact_ids[], kind, occurred_at}) и groups появляются
отдельной работой — код читает их через .get и без них возвращает пустые ряды.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from .tools import ToolError

MAX_BUCKETS = 100
DEFAULT_MONTHS = 12
DEFAULT_WEEKS = 12
TOP_GROUPS = 20
UNSPECIFIED = "Не указано"
MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
CONTACT_FIELDS = ("company", "city", "category", "priority", "tags", "source", "group")
_BIRTHDAY = re.compile(r"^(?:\d{4}|-)-(\d{2})-(\d{2})$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class ToolOutput:
    facts: dict[str, Any]
    blocks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AnalyticsTool:
    name: str
    description: str
    params: dict[str, Any]  # JSON-схема объекта параметров
    run: Callable[[AsyncIOMotorDatabase, dict], Awaitable[ToolOutput]]

    def spec(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.params}


# ---------------------------------------------------------------------------
# Проверка параметров
# ---------------------------------------------------------------------------


def _check_value(name: str, spec: dict, value: Any) -> Any:
    kind = spec.get("type")
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            raise ToolError(f"Параметр {name}: нужно целое число")
        value = int(value)
        if value < spec.get("minimum", value) or value > spec.get("maximum", value):
            raise ToolError(f"Параметр {name}: от {spec.get('minimum')} до {spec.get('maximum')}")
        return value
    if kind == "string":
        if not isinstance(value, str):
            raise ToolError(f"Параметр {name}: нужна строка")
        value = value.strip()
        if "enum" in spec and value not in spec["enum"]:
            raise ToolError(f"Параметр {name}: допустимо {', '.join(spec['enum'])}")
        if spec.get("format") == "date":
            try:
                if not _DATE.match(value):
                    raise ValueError
                date.fromisoformat(value)
            except ValueError:
                raise ToolError(f"Параметр {name}: дата в формате ГГГГ-ММ-ДД") from None
        if spec.get("format") == "object-id" and not ObjectId.is_valid(value):
            raise ToolError(f"Параметр {name}: неверный id")
        if len(value) > spec.get("maxLength", 100):
            raise ToolError(f"Параметр {name}: слишком длинное значение")
        return value
    raise ToolError(f"Параметр {name}: неподдерживаемый тип")


def validate_params(tool: AnalyticsTool, raw: Any) -> dict[str, Any]:
    """Параметры от модели → проверенные и дополненные значениями по умолчанию; иначе ToolError."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ToolError("Параметры инструмента должны быть объектом")
    props: dict[str, dict] = tool.params.get("properties", {})
    unknown = sorted(set(raw) - set(props))
    if unknown:
        raise ToolError(f"Инструмент {tool.name}: неизвестные параметры {', '.join(unknown)}")
    result: dict[str, Any] = {}
    for name, spec in props.items():
        if name in raw and raw[name] not in (None, ""):
            result[name] = _check_value(name, spec, raw[name])
        elif name in tool.params.get("required", []):
            raise ToolError(f"Инструмент {tool.name}: нужен параметр {name}")
        elif "default" in spec:
            result[name] = spec["default"]
    if result.get("from") and result.get("to") and result["from"] > result["to"]:
        raise ToolError("Начало периода позже конца")
    return result


# ---------------------------------------------------------------------------
# Данные и даты
# ---------------------------------------------------------------------------


def _dt(value: Any) -> Optional[datetime]:
    """datetime/дата/ISO-строка → datetime с UTC; непонятное → None."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _name(doc: dict) -> str:
    full = " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip()
    return full or doc.get("company") or "Без имени"


def _bucket_key(day: date, period: str) -> str:
    if period == "week":
        return (day - timedelta(days=day.weekday())).isoformat()
    return f"{day.year:04d}-{day.month:02d}"


def _bucket_keys(period: str, start: date, end: date) -> list[str]:
    """Все интервалы от start до end включительно; не больше MAX_BUCKETS последних."""
    keys: list[str] = []
    if period == "week":
        cursor = start - timedelta(days=start.weekday())
        while cursor <= end:
            keys.append(cursor.isoformat())
            cursor += timedelta(days=7)
    else:
        year, month = start.year, start.month
        while (year, month) <= (end.year, end.month):
            keys.append(f"{year:04d}-{month:02d}")
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return keys[-MAX_BUCKETS:]


def _range(params: dict, today: Optional[date] = None) -> tuple[date, date]:
    """Период: заданный или последние 12 месяцев / недель."""
    today = today or datetime.now(timezone.utc).date()
    end = date.fromisoformat(params["to"]) if params.get("to") else today
    if params.get("from"):
        return date.fromisoformat(params["from"]), end
    if params["period"] == "week":
        return end - timedelta(weeks=DEFAULT_WEEKS - 1), end
    month_index = end.year * 12 + end.month - 1 - (DEFAULT_MONTHS - 1)
    return date(month_index // 12, month_index % 12 + 1, 1), end


def _series(name: str, keys: list[str], counts: Counter) -> dict[str, Any]:
    return {"name": name, "points": [{"x": k, "y": counts.get(k, 0)} for k in keys]}


async def _contact_docs(db: AsyncIOMotorDatabase) -> list[dict]:
    return await db["contacts"].find({}).to_list(None)


async def _interaction_times(
    db: AsyncIOMotorDatabase, contact_id: Optional[str] = None
) -> list[tuple[list[str], datetime]]:
    """Взаимодействия: [(contact_ids, когда)]. Нет коллекции — пустой список."""
    query = {"contact_ids": contact_id} if contact_id else {}
    docs = await db["interactions"].find(query).to_list(None)
    result = []
    for doc in docs:
        when = _dt(doc.get("occurred_at"))
        if when:
            result.append(([str(c) for c in doc.get("contact_ids") or []], when))
    return result


async def _past_event_times(
    db: AsyncIOMotorDatabase, contact_id: Optional[str] = None, now: Optional[datetime] = None
) -> list[tuple[list[str], datetime]]:
    """Прошедшие события календаря, привязанные к людям: [(contact_ids, начало)]."""
    now = now or datetime.now(timezone.utc)
    query: dict[str, Any] = {"contact_ids": contact_id} if contact_id else {"contact_ids.0": {"$exists": True}}
    docs = await db["events"].find(query).to_list(None)
    result = []
    for doc in docs:
        when = _dt(doc.get("start"))
        if when and when <= now:
            result.append(([str(c) for c in doc.get("contact_ids") or []], when))
    return result


# ---------------------------------------------------------------------------
# Инструменты
# ---------------------------------------------------------------------------


async def _group_names(db: AsyncIOMotorDatabase) -> dict[str, str]:
    docs = await db["groups"].find({}).to_list(None)
    return {str(d["_id"]): d.get("name", "") for d in docs}


def _values_of(doc: dict, key: str, groups: dict[str, str]) -> list[str]:
    if key == "tags":
        raw = doc.get("tags")
    elif key == "group":
        raw = [groups.get(str(g), "") for g in doc.get("group_ids") or []]
    else:
        raw = doc.get(key)
    items = raw if isinstance(raw, list) else [raw]
    return [str(v).strip() for v in items if isinstance(v, (str, int)) and str(v).strip()]


async def count_contacts_by(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    key = params["field"]
    groups = await _group_names(db) if key == "group" else {}
    counts: Counter = Counter()
    shown: dict[str, str] = {}
    unspecified = 0
    docs = await _contact_docs(db)
    for doc in docs:
        values = _values_of(doc, key, groups)
        if not values:
            unspecified += 1
        for value in dict.fromkeys(v.casefold() for v in values):
            counts[value] += 1
        for v in values:
            shown.setdefault(v.casefold(), v)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], shown[kv[0]].casefold()))
    items = [(shown[k], n) for k, n in ranked[:TOP_GROUPS]]
    rest = sum(n for _, n in ranked[TOP_GROUPS:])
    if rest:
        items.append(("Другие", rest))
    if unspecified:
        items.append((UNSPECIFIED, unspecified))
    label = {"company": "компании", "city": "городу", "category": "категории", "priority": "приоритету",
             "tags": "тегам", "source": "источнику", "group": "группам"}[key]
    facts = {
        "field": key,
        "total_contacts": len(docs),
        "counts": [{"value": v, "count": n} for v, n in items],
    }
    blocks = []
    if items:
        blocks.append({
            "type": "chart",
            "chart": params.get("chart", "bar"),
            "title": f"Контакты по {label}",
            "x_label": key,
            "y_label": "Контактов",
            "series": [{"name": "Контактов", "points": [{"x": v, "y": n} for v, n in items]}],
        })
    return ToolOutput(facts, blocks)


async def interactions_over_time(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    period = params["period"]
    contact_id = params.get("contact_id")
    if contact_id and await db["contacts"].find_one({"_id": ObjectId(contact_id)}, {"_id": 1}) is None:
        raise ToolError("Контакт не найден")
    start, end = _range(params)
    keys = _bucket_keys(period, start, end)
    window = {k: True for k in keys}
    sources = {
        "Взаимодействия": await _interaction_times(db, contact_id),
        "Встречи в календаре": await _past_event_times(db, contact_id),
    }
    series = []
    for name, rows in sources.items():
        counts: Counter = Counter()
        for _, when in rows:
            key = _bucket_key(when.date(), period)
            if key in window:
                counts[key] += 1
        if counts:
            series.append(_series(name, keys, counts))
    unit = "неделям" if period == "week" else "месяцам"
    facts: dict[str, Any] = {
        "period": period, "from": keys[0] if keys else "", "to": keys[-1] if keys else "",
        "series": [{"name": s["name"], "total": sum(p["y"] for p in s["points"]), "points": s["points"]}
                   for s in series],
    }
    if not series:
        facts["note"] = "За выбранный период взаимодействий и встреч нет"
        return ToolOutput(facts)
    block = {"type": "chart", "chart": "line", "title": f"Взаимодействия по {unit}",
             "x_label": "Неделя" if period == "week" else "Месяц", "y_label": "Количество", "series": series}
    return ToolOutput(facts, [block])


async def birthdays_by_month(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    counts: Counter = Counter()
    for doc in await _contact_docs(db):
        match = _BIRTHDAY.match(str(doc.get("birthday") or ""))
        if match and 1 <= int(match.group(1)) <= 12:
            counts[int(match.group(1))] += 1
    points = [{"x": MONTHS_RU[m - 1], "y": counts.get(m, 0)} for m in range(1, 13)]
    facts = {"total_with_birthday": sum(counts.values()), "by_month": points}
    if not counts:
        facts["note"] = "Ни у одного контакта не указан день рождения"
        return ToolOutput(facts)
    block = {"type": "chart", "chart": "bar", "title": "Дни рождения по месяцам", "x_label": "Месяц",
             "y_label": "Контактов", "series": [{"name": "Дни рождения", "points": points}]}
    return ToolOutput(facts, [block])


async def contacts_added_over_time(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    period = params["period"]
    start, end = _range(params)
    keys = _bucket_keys(period, start, end)
    window = set(keys)
    counts: Counter = Counter()
    for doc in await _contact_docs(db):
        when = _dt(doc.get("created_at"))
        if when and _bucket_key(when.date(), period) in window:
            counts[_bucket_key(when.date(), period)] += 1
    series = _series("Новых контактов", keys, counts)
    facts = {"period": period, "total": sum(counts.values()), "points": series["points"]}
    unit = "неделям" if period == "week" else "месяцам"
    block = {"type": "chart", "chart": "line", "title": f"Новые контакты по {unit}",
             "x_label": "Неделя" if period == "week" else "Месяц", "y_label": "Контактов", "series": [series]}
    return ToolOutput(facts, [block] if keys else [])


async def top_contacts_by_interactions(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    limit = params["limit"]
    rows = await _interaction_times(db)
    source = "interactions"
    if not rows:  # взаимодействий нет — считаем встречи из календаря
        rows, source = await _past_event_times(db), "events"
    counts: Counter = Counter(cid for ids, _ in rows for cid in set(ids))
    names = {str(d["_id"]): _name(d) for d in await _contact_docs(db)}
    ranked = [(cid, n) for cid, n in counts.most_common() if cid in names][:limit]
    facts: dict[str, Any] = {"source": source, "top": [{"id": c, "name": names[c], "count": n} for c, n in ranked]}
    if not ranked:
        facts["note"] = "Данных о взаимодействиях нет"
        return ToolOutput(facts)
    chart = {"type": "chart", "chart": "bar", "title": "Контакты с наибольшим числом взаимодействий",
             "x_label": "Контакт", "y_label": "Взаимодействий",
             "series": [{"name": "Взаимодействий", "points": [{"x": names[c], "y": n} for c, n in ranked]}]}
    chips = {"type": "contacts", "contact_ids": [c for c, _ in ranked],
             "contacts": [{"id": c, "name": names[c]} for c, _ in ranked]}
    return ToolOutput(facts, [chart, chips])


async def stale_contacts(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    days, limit = params["days"], params["limit"]
    now = datetime.now(timezone.utc)
    last: dict[str, datetime] = {}
    for ids, when in [*await _interaction_times(db), *await _past_event_times(db, now=now)]:
        for cid in ids:
            if cid not in last or when > last[cid]:
                last[cid] = when
    cutoff = now - timedelta(days=days)
    contacted, never = [], []
    for doc in await _contact_docs(db):
        cid = str(doc["_id"])
        if cid not in last:
            never.append((cid, _name(doc), None))
        elif last[cid] < cutoff:
            contacted.append((cid, _name(doc), last[cid]))
    contacted.sort(key=lambda r: r[2])
    never.sort(key=lambda r: r[1].casefold())
    shown = [*contacted, *never][:limit]
    facts: dict[str, Any] = {
        "days": days, "stale_total": len(contacted), "never_contacted_total": len(never),
        "shown": [{"id": c, "name": n, "last_contact": w.date().isoformat() if w else None} for c, n, w in shown],
    }
    if not shown:
        facts["note"] = f"Нет контактов, с которыми не общались больше {days} дн."
        return ToolOutput(facts)
    rows = [
        {"name": n, "last_contact": w.date().isoformat() if w else "никогда", "days": (now - w).days if w else None}
        for _, n, w in shown
    ]
    table = {"type": "table", "title": f"Давно не общались (больше {days} дн.)",
             "columns": [{"key": "name", "label": "Контакт"}, {"key": "last_contact", "label": "Последний контакт"},
                         {"key": "days", "label": "Дней назад"}], "rows": rows}
    chips = {"type": "contacts", "contact_ids": [c for c, _, _ in shown],
             "contacts": [{"id": c, "name": n} for c, n, _ in shown]}
    return ToolOutput(facts, [table, chips])


async def goal_progress(db: AsyncIOMotorDatabase, params: dict) -> ToolOutput:
    """Выполнение целей активной стратегии (основной подход): процент выполнения по каждой цели."""
    from ..repositories import goals as goals_repo
    from ..services import strategy

    state = await goals_repo.get_state(db)
    if not state["primary"]:
        return ToolOutput({"note": "Стратегия не выбрана: подход задаётся на странице «Цели»"})
    metrics = strategy.compute_all_metrics(state, await goals_repo.metrics_context(db, state, params["period"]))
    primary = metrics["approaches"][0]
    series = strategy.goal_progress_series(metrics)
    facts = {"approach": primary["name"], "period_days": params["period"], "targets": primary["targets"],
             "hints": primary["hints"]}
    if not series["points"]:
        facts["note"] = "У выбранного подхода пока нет числовых целей"
        return ToolOutput(facts)
    block = {"type": "chart", "chart": "bar", "title": f"Цели: {primary['name']}", "x_label": "Цель",
             "y_label": "Выполнено, %", "series": [{"name": "Выполнение цели", "points": series["points"]}]}
    return ToolOutput(facts, [block])


# ---------------------------------------------------------------------------
# Реестр
# ---------------------------------------------------------------------------

_DATE_PROP = {"type": "string", "format": "date"}
_PERIOD_PROP = {"type": "string", "enum": ["week", "month"], "default": "month"}

ANALYTICS_TOOLS: dict[str, AnalyticsTool] = {
    t.name: t
    for t in (
        AnalyticsTool(
            "count_contacts_by",
            "Сколько контактов в каждой группе по полю: компании, города, категории, приоритеты, теги, источники, группы. "
            "Для вопросов «сколько у меня контактов по городам», «распределение по компаниям».",
            {"type": "object", "properties": {
                "field": {"type": "string", "enum": list(CONTACT_FIELDS)},
                "chart": {"type": "string", "enum": ["bar", "pie"], "default": "bar"},
            }, "required": ["field"], "additionalProperties": False},
            count_contacts_by,
        ),
        AnalyticsTool(
            "interactions_over_time",
            "Динамика взаимодействий и встреч по неделям или месяцам (общая или по одному контакту). "
            "Для вопросов «динамика встреч», «как часто я общаюсь».",
            {"type": "object", "properties": {
                "period": _PERIOD_PROP, "from": _DATE_PROP, "to": _DATE_PROP,
                "contact_id": {"type": "string", "format": "object-id"},
            }, "required": [], "additionalProperties": False},
            interactions_over_time,
        ),
        AnalyticsTool(
            "birthdays_by_month",
            "Сколько дней рождения контактов приходится на каждый месяц года.",
            {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            birthdays_by_month,
        ),
        AnalyticsTool(
            "contacts_added_over_time",
            "Сколько новых контактов добавлено по неделям или месяцам (рост базы).",
            {"type": "object", "properties": {
                "period": _PERIOD_PROP, "from": _DATE_PROP, "to": _DATE_PROP,
            }, "required": [], "additionalProperties": False},
            contacts_added_over_time,
        ),
        AnalyticsTool(
            "top_contacts_by_interactions",
            "Контакты, с которыми взаимодействий больше всего («с кем я общаюсь чаще всего»).",
            {"type": "object", "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
            }, "required": [], "additionalProperties": False},
            top_contacts_by_interactions,
        ),
        AnalyticsTool(
            "stale_contacts",
            "Контакты, с которыми давно не было взаимодействий (дольше N дней), «с кем я давно не общался».",
            {"type": "object", "properties": {
                "days": {"type": "integer", "minimum": 1, "maximum": 3650, "default": 90},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            }, "required": [], "additionalProperties": False},
            stale_contacts,
        ),
        AnalyticsTool(
            "goal_progress",
            "Как выполняются цели выбранной стратегии общения (подход на странице «Цели»): % выполнения по целям. "
            "Для вопросов «как мои цели», «выполняю ли я стратегию».",
            {"type": "object", "properties": {
                "period": {"type": "integer", "minimum": 30, "maximum": 180, "default": 30},
            }, "required": [], "additionalProperties": False},
            goal_progress,
        ),
    )
}


def tool_specs() -> list[dict[str, Any]]:
    """Описания инструментов для модели и MCP: имя, описание, JSON-схема параметров."""
    return [t.spec() for t in ANALYTICS_TOOLS.values()]


async def run_tool(db: AsyncIOMotorDatabase, name: str, raw_params: Any = None) -> ToolOutput:
    """Выполнить инструмент по имени от модели: имя и параметры проверяются строго."""
    tool = ANALYTICS_TOOLS.get(name) if isinstance(name, str) else None
    if tool is None:
        raise ToolError(f"Неизвестный инструмент: {str(name)[:50]}")
    return await tool.run(db, validate_params(tool, raw_params))
