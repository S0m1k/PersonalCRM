"""
Стратегии общения: каталог подходов, рекомендации частоты, метрики выполнения, «следующие шаги».

Чистая логика без IO: данные (контакты, взаимодействия, назначения кругов) приходят аргументами,
собирает их repositories/goals.py. Подход = шаблон: описание, правила и метрики.

  max_contacts   — широкая сеть, слабые связи (Грановеттер)
  deep_relations — круги Данбара, каждому кругу своя частота и ёмкость
  life_balance   — колесо баланса: сферы жизни и целевое число касаний в месяц
  custom         — свои правила «сегмент → частота»

Рекомендация подхода — частота для контакта и причина. Основной подход главнее, дополнительные
дают рекомендацию только тем, кому основной её не дал.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from ..models.goals import APPROACH_IDS, default_settings

NEXT_STEPS_LIMIT = 10
SERIES_MONTHS = 6
RADAR_CAP_PCT = 150
HIGH_PRIORITIES = ("top", "high")
MIN_BOOSTED_DAYS = 30
SPHERE_MIN_DAYS, SPHERE_MAX_DAYS = 7, 365
LAGGING_PCT, EXCESS_PCT = 50, 150
MONTHS_RU = ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"]
CIRCLE_NAMES = {1: "Ближний круг", 2: "Близкие", 3: "Приятели", 4: "Знакомые"}

# ---------------------------------------------------------------------------
# Каталог
# ---------------------------------------------------------------------------

CATALOGUE: list[dict[str, Any]] = [
    {
        "id": "max_contacts",
        "name": "Максимум контактов",
        "icon": "network",
        "tagline": "Широкая сеть: новые знакомства и лёгкие касания, сила слабых связей.",
        "philosophy": (
            "Социолог Марк Грановеттер показал: новые возможности чаще приходят не от близких друзей, а от "
            "знакомых из других кругов. Поэтому важны ширина сети и разнообразие, а не глубина каждой связи."
        ),
        "principles": [
            "Регулярно знакомиться с новыми людьми.",
            "Большинству людей достаточно редкого лёгкого касания.",
            "Следить, чтобы за полгода вы коснулись большей части сети.",
            "Ценить разнообразие: разные компании, города, профессии.",
        ],
        "does": [
            "Предложит одну редкую частоту для большинства контактов (по умолчанию раз в 120 дней), "
            "для приоритетных людей вдвое чаще.",
            "Покажет, сколько новых знакомств за месяц и какая доля сети тронута за полгода.",
        ],
        "metrics": ["Новых контактов в месяц", "Доля сети, тронутой за период", "Разнообразие: компании и города"],
    },
    {
        "id": "deep_relations",
        "name": "Глубокие отношения",
        "icon": "heart",
        "tagline": "Круги Данбара: мало людей, но по-настоящему близко.",
        "philosophy": (
            "Антрополог Робин Данбар оценил, что человек способен поддерживать около 150 стабильных связей, "
            "и они делятся на круги примерно по 5, 15, 50 и 150 человек. Чем ближе круг, тем чаще нужны касания."
        ),
        "principles": [
            "Распределите людей по четырём кругам близости.",
            "У каждого круга своя частота общения: от недели до года.",
            "Круги ограничены: перегруженный круг значит, что кого-то пора перевести дальше.",
            "Внутренний круг — главный приоритет времени и внимания.",
        ],
        "does": [
            "Назначит частоту по кругу контакта: 7 / 30 / 90 / 365 дней по умолчанию.",
            "Предупредит, если в круге больше людей, чем помещается.",
            "Покажет, какая доля каждого круга на графике общения.",
        ],
        "metrics": ["Доля круга «по графику»", "Переполнение круга", "Среднее число дней с последнего контакта"],
    },
    {
        "id": "life_balance",
        "name": "Колесо жизненного баланса",
        "icon": "pie",
        "tagline": "Равномерное внимание ко всем сферам жизни.",
        "philosophy": (
            "Колесо баланса оценивает жизнь по сферам: семья, друзья, работа, здоровье, развитие, отдых, "
            "сообщество. Перекос в одну сферу делает колесо «квадратным»; цель — гладкий круг."
        ),
        "principles": [
            "Каждый контакт привязан к одной или нескольким сферам (поле «сферы жизни»).",
            "Для каждой сферы задано целевое число касаний в месяц.",
            "Просевшая сфера — сигнал найти в ней людей и написать им.",
            "Список сфер можно менять под себя.",
        ],
        "does": [
            "Посчитает частоту для людей сферы: чем больше людей и выше цель, тем чаще касания.",
            "Нарисует колесо: фактические касания против цели по каждой сфере.",
            "Подскажет, какая сфера отстаёт, а какая перегружена.",
        ],
        "metrics": ["Касания по сферам за 30 / 90 дней", "Выполнение цели по сфере", "Доли сфер"],
    },
    {
        "id": "custom",
        "name": "Свой подход",
        "icon": "sliders",
        "tagline": "Правила, которые вы задаёте сами.",
        "philosophy": "Свои правила вида «сегмент → частота» плюс месячные цели по знакомствам и касаниям.",
        "principles": [
            "Сегмент: тег, группа, приоритет, сфера жизни или круг Данбара.",
            "Если контакт попал в несколько правил, берётся самая частая.",
            "По желанию — цели на месяц: новые знакомства и число касаний.",
        ],
        "does": [
            "Назначит частоту по первому подходящему сегменту.",
            "Покажет выполнение каждого правила и месячных целей.",
        ],
        "metrics": ["Доля контактов по графику в каждом правиле", "Новые знакомства", "Касания в месяц"],
    },
]


def catalogue() -> list[dict[str, Any]]:
    defaults = default_settings()
    return [{**item, "defaults": defaults[item["id"]]} for item in CATALOGUE]


def approach_name(approach_id: str) -> str:
    return next((a["name"] for a in CATALOGUE if a["id"] == approach_id), approach_id)


# ---------------------------------------------------------------------------
# Вход: контакты и касания
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContactView:
    id: str
    name: str = "Без имени"
    created_at: Optional[datetime] = None
    priority: str = ""
    tags: tuple[str, ...] = ()
    group_ids: tuple[str, ...] = ()
    life_areas: tuple[str, ...] = ()
    company: str = ""
    city: str = ""
    frequency_days: Optional[int] = None
    snoozed_until: Optional[date] = None
    last_at: Optional[datetime] = None


@dataclass(frozen=True)
class Recommendation:
    contact_id: str
    frequency_days: int
    reason: str
    approach: str


def _aware(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return None


def _date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _folded(items: Any) -> tuple[str, ...]:
    return tuple(str(i).strip().casefold() for i in (items or []) if str(i).strip())


def contact_view(doc: dict, last: Optional[datetime] = None) -> ContactView:
    """Документ контакта из Mongo → нормализованное представление."""
    kit = doc.get("keep_in_touch") or {}
    stored_last = _aware(doc.get("last_interaction_at"))
    lasts = [d for d in (_aware(last), stored_last) if d]
    name = " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip()
    freq = kit.get("frequency_days")
    return ContactView(
        id=str(doc["_id"]),
        name=name or doc.get("company") or "Без имени",
        created_at=_aware(doc.get("created_at")),
        priority=str(doc.get("priority") or "").strip().lower(),
        tags=_folded(doc.get("tags")),
        group_ids=tuple(str(g) for g in doc.get("group_ids") or []),
        life_areas=_folded(doc.get("life_areas")),
        company=str(doc.get("company") or "").strip(),
        city=str(doc.get("city") or "").strip(),
        frequency_days=int(freq) if freq else None,
        snoozed_until=_date(kit.get("snoozed_until")),
        last_at=max(lasts) if lasts else None,
    )


def _circle_of(assignments: dict, contact_id: str) -> Optional[int]:
    value = (assignments.get(contact_id) or {}).get("circle")
    return value if value in (1, 2, 3, 4) else None


def days_since(contact: ContactView, now: datetime) -> Optional[int]:
    """Дней с последнего контакта; None — контактов не было."""
    return max((now - contact.last_at).days, 0) if contact.last_at else None


def _anchor_days(contact: ContactView, now: datetime) -> int:
    """Сколько дней «ждёт» контакт: с последнего касания, а без касаний — с создания."""
    anchor = contact.last_at or contact.created_at or now
    return max((now - anchor).days, 0)


def is_on_schedule(contact: ContactView, frequency_days: int, now: datetime) -> bool:
    return _anchor_days(contact, now) <= frequency_days


# ---------------------------------------------------------------------------
# Рекомендации по подходам
# ---------------------------------------------------------------------------


def _recommend_max_contacts(settings: dict, contacts: list[ContactView], assignments: dict) -> dict[str, Recommendation]:
    base = settings["frequency_days"]
    result = {}
    for c in contacts:
        if c.priority in HIGH_PRIORITIES:
            days = max(base // 2, MIN_BOOSTED_DAYS)
            reason = f"Широкая сеть: приоритетный человек, раз в {days} дн."
        else:
            days, reason = base, f"Широкая сеть: лёгкое касание раз в {base} дн."
        result[c.id] = Recommendation(c.id, days, reason, "max_contacts")
    return result


def _recommend_deep(settings: dict, contacts: list[ContactView], assignments: dict) -> dict[str, Recommendation]:
    circles = settings["circles"]
    result = {}
    for c in contacts:
        circle = _circle_of(assignments, c.id)
        if circle is None:
            continue
        days = circles[circle - 1]["frequency_days"]
        result[c.id] = Recommendation(
            c.id, days, f"Круг {circle} ({CIRCLE_NAMES[circle]}): раз в {days} дн.", "deep_relations"
        )
    return result


def _sphere_frequencies(settings: dict, contacts: list[ContactView]) -> dict[str, tuple[int, str]]:
    """{contact_id: (частота, сфера)} — самая частая из сфер контакта."""
    members: dict[str, list[str]] = {}
    for c in contacts:
        for area in c.life_areas:
            members.setdefault(area, []).append(c.id)
    best: dict[str, tuple[int, str]] = {}
    for sphere in settings["spheres"]:
        ids = members.get(sphere["name"].casefold(), [])
        target = sphere["target_per_month"]
        if not ids or target <= 0:
            continue
        days = min(max(round(30 * len(ids) / target), SPHERE_MIN_DAYS), SPHERE_MAX_DAYS)
        for cid in ids:
            if cid not in best or days < best[cid][0]:
                best[cid] = (days, sphere["name"])
    return best


def _recommend_life(settings: dict, contacts: list[ContactView], assignments: dict) -> dict[str, Recommendation]:
    return {
        cid: Recommendation(cid, days, f"Сфера «{name}»: раз в {days} дн. для цели по сфере", "life_balance")
        for cid, (days, name) in _sphere_frequencies(settings, contacts).items()
    }


def _matches(rule: dict, contact: ContactView, assignments: dict) -> bool:
    kind, value = rule["kind"], str(rule["value"]).strip().casefold()
    if kind == "tag":
        return value in contact.tags
    if kind == "group":
        return rule["value"] in contact.group_ids
    if kind == "priority":
        return value == contact.priority
    if kind == "life_area":
        return value in contact.life_areas
    if kind == "circle":
        return value == str(_circle_of(assignments, contact.id))
    return False


def _rule_label(rule: dict) -> str:
    names = {"tag": "тег", "group": "группа", "priority": "приоритет", "life_area": "сфера", "circle": "круг"}
    return f"{names[rule['kind']]} «{rule['value']}»"


def _recommend_custom(settings: dict, contacts: list[ContactView], assignments: dict) -> dict[str, Recommendation]:
    result = {}
    for c in contacts:
        hits = [r for r in settings["rules"] if _matches(r, c, assignments)]
        if hits:
            rule = min(hits, key=lambda r: r["frequency_days"])
            result[c.id] = Recommendation(
                c.id, rule["frequency_days"], f"Правило ({_rule_label(rule)}): раз в {rule['frequency_days']} дн.", "custom"
            )
    return result


_RECOMMENDERS = {
    "max_contacts": _recommend_max_contacts,
    "deep_relations": _recommend_deep,
    "life_balance": _recommend_life,
    "custom": _recommend_custom,
}


def recommend(approach: str, settings: dict, contacts: list[ContactView], assignments: dict) -> dict[str, Recommendation]:
    """Рекомендации одного подхода: {contact_id: Recommendation}."""
    return _RECOMMENDERS[approach](settings, contacts, assignments)


def active_approaches(state: dict) -> list[str]:
    """Основной подход первым, затем дополнительные без повторов."""
    order = [state.get("primary"), *(state.get("enabled") or [])]
    return [a for i, a in enumerate(order) if a in APPROACH_IDS and a not in order[:i]]


def effective_recommendations(state: dict, contacts: list[ContactView]) -> dict[str, Recommendation]:
    """Итоговая рекомендация для каждого контакта: основной подход, а где его нет — дополнительные по порядку."""
    settings = {**default_settings(), **(state.get("settings") or {})}
    assignments = state.get("assignments") or {}
    result: dict[str, Recommendation] = {}
    for approach in active_approaches(state):
        for cid, rec in recommend(approach, settings[approach], contacts, assignments).items():
            result.setdefault(cid, rec)
    return result


# ---------------------------------------------------------------------------
# Следующие шаги
# ---------------------------------------------------------------------------


def next_steps(
    state: dict, contacts: list[ContactView], now: datetime, limit: int = NEXT_STEPS_LIMIT
) -> list[dict[str, Any]]:
    """Кому написать сейчас: просроченные относительно рекомендованной частоты, самые запущенные первыми."""
    recs = effective_recommendations(state, contacts)
    today = now.date()
    rows = []
    for c in contacts:
        rec = recs.get(c.id)
        if rec is None or (c.snoozed_until and c.snoozed_until >= today):
            continue
        waiting = _anchor_days(c, now)
        if waiting < rec.frequency_days:
            continue
        rows.append((waiting / rec.frequency_days, HIGH_PRIORITIES.count(c.priority), c, rec, waiting))
    rows.sort(key=lambda r: (-r[0], -r[1], r[2].name.casefold()))
    return [
        {
            "contact_id": c.id,
            "name": c.name,
            "frequency_days": rec.frequency_days,
            "days_since": days_since(c, now),
            "days_overdue": waiting - rec.frequency_days,
            "approach": rec.approach,
            "reason": _step_reason(c, rec, waiting, now),
        }
        for _, _, c, rec, waiting in rows[:limit]
    ]


def _step_reason(c: ContactView, rec: Recommendation, waiting: int, now: datetime) -> str:
    since = "ещё не общались" if c.last_at is None else f"не общались {waiting} дн."
    return f"{rec.reason[:-1] if rec.reason.endswith('.') else rec.reason}; {since}"


# ---------------------------------------------------------------------------
# Применение к контактам
# ---------------------------------------------------------------------------


def preview_apply(
    state: dict, contacts: list[ContactView], overwrite: bool = False
) -> dict[str, Any]:
    """
    Что изменится, если применить стратегию. Ручной считается частота, которой нет среди ранее применённых
    стратегией (state['applied'] = {contact_id: частота}); её меняем только при overwrite.
    """
    recs = effective_recommendations(state, contacts)
    applied = state.get("applied") or {}
    items, by_frequency = [], {}
    counts = {"change": 0, "same": 0, "skipped_manual": 0}
    for c in contacts:
        rec = recs.get(c.id)
        if rec is None:
            continue
        manual = c.frequency_days is not None and applied.get(c.id) != c.frequency_days
        if c.frequency_days == rec.frequency_days:
            action = "same"
        elif manual and not overwrite:
            action = "skipped_manual"
        else:
            action = "change"
        counts[action] += 1
        if action == "change":
            by_frequency[rec.frequency_days] = by_frequency.get(rec.frequency_days, 0) + 1
        items.append(
            {
                "contact_id": c.id, "name": c.name, "current": c.frequency_days, "recommended": rec.frequency_days,
                "reason": rec.reason, "action": action, "was_manual": manual,
            }
        )
    items.sort(key=lambda i: (i["action"] != "change", i["name"].casefold()))
    return {
        "will_change": counts["change"],
        "unchanged": counts["same"],
        "skipped_manual": counts["skipped_manual"],
        "by_frequency": [{"frequency_days": d, "count": n} for d, n in sorted(by_frequency.items())],
        "items": items,
        "overwrite": overwrite,
    }


# ---------------------------------------------------------------------------
# Метрики
# ---------------------------------------------------------------------------


@dataclass
class MetricsContext:
    contacts: list[ContactView]
    touches: list[tuple[list[str], datetime]]  # (contact_ids, когда) — взаимодействия и прошедшие события
    assignments: dict
    now: datetime
    period: int = 30
    contacts_by_id: dict[str, ContactView] = field(init=False)

    def __post_init__(self) -> None:
        self.contacts_by_id = {c.id: c for c in self.contacts}

    def touches_in(self, days: int) -> list[list[str]]:
        since = self.now - timedelta(days=days)
        return [ids for ids, when in self.touches if since <= when <= self.now]


def _target(key: str, label: str, value: float, target: float, unit: str = "") -> dict[str, Any]:
    progress = 1.0 if target <= 0 else min(value / target, 1.0)
    return {
        "key": key, "label": label, "value": round(value, 1), "target": round(target, 1),
        "unit": unit, "progress": round(progress, 3),
    }


def _pct(part: int, whole: int) -> Optional[float]:
    return round(100 * part / whole, 1) if whole else None


def _month_keys(now: datetime, count: int) -> list[str]:
    index = now.year * 12 + now.month - 1
    return [f"{(index - i) // 12:04d}-{(index - i) % 12 + 1:02d}" for i in range(count - 1, -1, -1)]


def new_contacts_series(contacts: list[ContactView], now: datetime, months: int = SERIES_MONTHS) -> list[dict[str, Any]]:
    keys = _month_keys(now, months)
    counts = dict.fromkeys(keys, 0)
    for c in contacts:
        if c.created_at:
            key = f"{c.created_at.year:04d}-{c.created_at.month:02d}"
            if key in counts:
                counts[key] += 1
    return [{"x": k, "label": MONTHS_RU[int(k[5:]) - 1], "y": counts[k]} for k in keys]


def _metrics_max(settings: dict, ctx: MetricsContext) -> dict[str, Any]:
    series = new_contacts_series(ctx.contacts, ctx.now)
    window = settings["coverage_window_days"]
    since = ctx.now - timedelta(days=window)
    touched = [c for c in ctx.contacts if c.last_at and c.last_at >= since]
    coverage = _pct(len(touched), len(ctx.contacts)) or 0.0
    companies = {c.company.casefold() for c in ctx.contacts if c.company}
    cities = {c.city.casefold() for c in ctx.contacts if c.city}
    hints = []
    if series[-1]["y"] < settings["new_per_month"]:
        hints.append(f"В этом месяце {series[-1]['y']} новых знакомств из {settings['new_per_month']}: пора расширять сеть.")
    if ctx.contacts and coverage < settings["coverage_target_pct"]:
        hints.append(f"За {window} дн. тронуто {coverage:.0f}% сети при цели {settings['coverage_target_pct']}%.")
    return {
        "targets": [
            _target("new_contacts", "Новых знакомств в этом месяце", series[-1]["y"], settings["new_per_month"]),
            _target("coverage", f"Сеть тронута за {window} дн.", coverage, settings["coverage_target_pct"], "%"),
        ],
        "new_per_month": series,
        "coverage": {"touched": len(touched), "total": len(ctx.contacts), "pct": coverage, "window_days": window},
        "diversity": {"companies": len(companies), "cities": len(cities)},
        "hints": hints,
    }


def _metrics_deep(settings: dict, ctx: MetricsContext) -> dict[str, Any]:
    rows, hints = [], []
    on_total = assigned_total = 0
    for number, circle in enumerate(settings["circles"], start=1):
        members = [c for c in ctx.contacts if _circle_of(ctx.assignments, c.id) == number]
        on = sum(1 for c in members if is_on_schedule(c, circle["frequency_days"], ctx.now))
        since = [d for d in (days_since(c, ctx.now) for c in members) if d is not None]
        overflow = max(len(members) - circle["capacity"], 0)
        on_total, assigned_total = on_total + on, assigned_total + len(members)
        rows.append(
            {
                "circle": number, "name": CIRCLE_NAMES[number], "capacity": circle["capacity"],
                "frequency_days": circle["frequency_days"], "count": len(members), "overflow": overflow,
                "on_schedule": on, "overdue": len(members) - on, "free": max(circle["capacity"] - len(members), 0),
                "on_schedule_pct": _pct(on, len(members)),
                "avg_days_since": round(sum(since) / len(since), 1) if since else None,
            }
        )
        if overflow:
            hints.append(f"Круг {number} переполнен на {overflow}: переведите часть людей в следующий круг.")
    unassigned = len(ctx.contacts) - assigned_total
    if unassigned and ctx.contacts:
        hints.append(f"{unassigned} контактов не распределены по кругам.")
    overall = _pct(on_total, assigned_total) or 0.0
    return {
        "targets": [_target("on_schedule", "Людей из кругов общаются по графику", overall, 100, "%")],
        "circles": rows,
        "unassigned": unassigned,
        "hints": hints,
    }


def _sphere_stats(settings: dict, ctx: MetricsContext, days: int) -> list[dict[str, Any]]:
    touches = ctx.touches_in(days)
    total_target = sum(s["target_per_month"] for s in settings["spheres"]) or 1
    counts: dict[str, int] = {}
    for ids in touches:
        areas = {a for cid in ids if cid in ctx.contacts_by_id for a in ctx.contacts_by_id[cid].life_areas}
        for area in areas:
            counts[area] = counts.get(area, 0) + 1
    total_actual = sum(counts.get(s["name"].casefold(), 0) for s in settings["spheres"]) or 1
    rows = []
    for sphere in settings["spheres"]:
        key = sphere["name"].casefold()
        actual = counts.get(key, 0)
        per_month = actual * 30 / days
        target = sphere["target_per_month"]
        rows.append(
            {
                "name": sphere["name"], "target_per_month": target, "touches": actual,
                "per_month": round(per_month, 1),
                "contacts": sum(1 for c in ctx.contacts if key in c.life_areas),
                "pct_of_target": round(100 * per_month / target) if target > 0 else None,
                "share_actual": round(100 * actual / total_actual, 1),
                "share_target": round(100 * target / total_target, 1),
            }
        )
    return rows


def _metrics_life(settings: dict, ctx: MetricsContext) -> dict[str, Any]:
    spheres = _sphere_stats(settings, ctx, ctx.period)
    hints = []
    for s in spheres:
        pct = s["pct_of_target"]
        if pct is None:
            continue
        if s["contacts"] == 0:
            hints.append(f"В сфере «{s['name']}» нет контактов: отметьте людей полем «сферы жизни».")
        elif pct < LAGGING_PCT:
            hints.append(f"Сфера «{s['name']}» просела: касаний в месяц {s['per_month']:g} при цели {s['target_per_month']:g}.")
        elif pct > EXCESS_PCT:
            hints.append(f"В сфере «{s['name']}» касаний вдвое больше цели: перекос в её сторону.")
    scored = [min(s["pct_of_target"], 100) for s in spheres if s["pct_of_target"] is not None]
    balance = round(sum(scored) / len(scored), 1) if scored else 0.0
    return {
        "targets": [_target("balance", "Выполнение целей по сферам", balance, 100, "%")],
        "period_days": ctx.period,
        "spheres": spheres,
        "radar": _radar(spheres),
        "radar_by_period": {str(d): _radar(_sphere_stats(settings, ctx, d)) for d in (30, 90)},
        "unassigned": sum(1 for c in ctx.contacts if not c.life_areas),
        "hints": hints,
    }


def _radar(spheres: list[dict]) -> list[dict]:
    return [
        {"sphere": s["name"], "actual": min(s["pct_of_target"] or 0, RADAR_CAP_PCT), "target": 100}
        for s in spheres if s["pct_of_target"] is not None
    ]


def _metrics_custom(settings: dict, ctx: MetricsContext) -> dict[str, Any]:
    rules, targets, hints = [], [], []
    for rule in settings["rules"]:
        members = [c for c in ctx.contacts if _matches(rule, c, ctx.assignments)]
        on = sum(1 for c in members if is_on_schedule(c, rule["frequency_days"], ctx.now))
        rules.append(
            {
                "label": _rule_label(rule), "frequency_days": rule["frequency_days"], "count": len(members),
                "on_schedule": on, "on_schedule_pct": _pct(on, len(members)),
            }
        )
        if not members:
            hints.append(f"Под правило ({_rule_label(rule)}) не попал ни один контакт.")
    series = new_contacts_series(ctx.contacts, ctx.now)
    if settings.get("new_per_month") is not None:
        targets.append(_target("new_contacts", "Новых знакомств в этом месяце", series[-1]["y"], settings["new_per_month"]))
    if settings.get("touches_per_month") is not None:
        per_month = len(ctx.touches_in(ctx.period)) * 30 / ctx.period
        targets.append(_target("touches", "Касаний в месяц", per_month, settings["touches_per_month"]))
    return {"targets": targets, "rules": rules, "new_per_month": series, "hints": hints}


_METRICS = {
    "max_contacts": _metrics_max,
    "deep_relations": _metrics_deep,
    "life_balance": _metrics_life,
    "custom": _metrics_custom,
}


def compute_metrics(approach: str, settings: dict, ctx: MetricsContext) -> dict[str, Any]:
    return {"id": approach, "name": approach_name(approach), "period_days": ctx.period, **_METRICS[approach](settings, ctx)}


def compute_all_metrics(state: dict, ctx: MetricsContext) -> dict[str, Any]:
    """Метрики основного и дополнительных подходов."""
    settings = {**default_settings(), **(state.get("settings") or {})}
    approaches = [compute_metrics(a, settings[a], ctx) for a in active_approaches(state)]
    return {"period": ctx.period, "primary": state.get("primary"), "approaches": approaches}


def goal_progress_series(metrics: dict[str, Any]) -> dict[str, Any]:
    """Метрики основного подхода → одна серия «цель / факт» для графика ассистента."""
    approaches = metrics.get("approaches") or []
    if not approaches:
        return {"approach": None, "points": []}
    primary = approaches[0]
    points = [{"x": t["label"], "y": round(100 * t["progress"], 1)} for t in primary.get("targets", [])]
    return {"approach": primary["name"], "points": points}

