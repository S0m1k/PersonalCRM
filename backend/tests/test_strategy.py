"""
Движок стратегий (чистые функции): рекомендации, метрики, следующие шаги, применение.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from bson import ObjectId

from app.models.goals import default_settings, validate_settings
from app.services import strategy as st

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


def view(name="Анна", last=None, created=400, **kw) -> st.ContactView:
    return st.ContactView(id=str(ObjectId()), name=name, created_at=ago(created), last_at=last, **kw)


def state(primary, enabled=(), assignments=None, applied=None, **settings) -> dict:
    merged = default_settings()
    for approach, values in settings.items():
        merged[approach] = validate_settings(approach, values)
    return {
        "primary": primary, "enabled": list(enabled), "settings": merged,
        "assignments": assignments or {}, "applied": applied or {},
    }


def ctx(contacts, touches=(), assignments=None, period=30) -> st.MetricsContext:
    return st.MetricsContext(list(contacts), list(touches), assignments or {}, NOW, period)


# --- каталог и настройки ------------------------------------------------------------------------


def test_catalogue_has_four_approaches_with_defaults():
    items = st.catalogue()

    assert [i["id"] for i in items] == ["max_contacts", "deep_relations", "life_balance", "custom"]
    for item in items:
        assert item["principles"] and item["does"] and item["metrics"] and item["defaults"] is not None
    assert items[0]["defaults"]["new_per_month"] == 8


@pytest.mark.parametrize(
    "approach, raw",
    [
        ("max_contacts", {"new_per_month": -1}),
        ("max_contacts", {"frequency_days": 5}),
        ("max_contacts", {"evil": 1}),
        ("deep_relations", {"circles": [{"capacity": 5, "frequency_days": 7}]}),
        ("life_balance", {"spheres": [{"name": "А", "target_per_month": 1}, {"name": "а", "target_per_month": 1}]}),
        ("custom", {"rules": [{"kind": "color", "value": "x", "frequency_days": 10}]}),
        ("custom", {"rules": [{"kind": "tag", "value": "x", "frequency_days": 0}]}),
        ("nope", {}),
    ],
)
def test_invalid_settings_are_rejected(approach, raw):
    with pytest.raises(ValueError):
        validate_settings(approach, raw)


# --- рекомендации -------------------------------------------------------------------------------


def test_max_contacts_gives_light_touch_and_boosts_priority():
    plain, vip = view("Обычный"), view("Важный", priority="top")

    recs = st.recommend("max_contacts", default_settings()["max_contacts"], [plain, vip], {})

    assert recs[plain.id].frequency_days == 120
    assert recs[vip.id].frequency_days == 60
    assert "120" in recs[plain.id].reason


def test_boost_never_goes_below_minimum():
    vip = view(priority="high")
    settings = {**default_settings()["max_contacts"], "frequency_days": 40}

    assert st.recommend("max_contacts", settings, [vip], {})[vip.id].frequency_days == 30


def test_deep_relations_uses_circle_frequency_and_skips_unassigned():
    a, b, c = view("А"), view("Б"), view("В")
    assignments = {a.id: {"circle": 1}, b.id: {"circle": 3}}

    recs = st.recommend("deep_relations", default_settings()["deep_relations"], [a, b, c], assignments)

    assert recs[a.id].frequency_days == 7 and recs[b.id].frequency_days == 90
    assert c.id not in recs
    assert "Круг 1" in recs[a.id].reason


def test_life_balance_frequency_from_sphere_target_and_size():
    family = [view(f"С{i}", life_areas=("семья",)) for i in range(4)]
    solo = view("Один", life_areas=("здоровье",))
    nobody = view("Без сферы")

    recs = st.recommend("life_balance", default_settings()["life_balance"], [*family, solo, nobody], {})

    assert recs[family[0].id].frequency_days == 15  # 30 * 4 / 8 касаний
    assert recs[solo.id].frequency_days == 15  # 30 * 1 / 2
    assert nobody.id not in recs


def test_life_balance_takes_the_most_frequent_sphere_and_clamps():
    both = view("Оба", life_areas=("семья", "друзья"))
    settings = validate_settings("life_balance", {"spheres": [
        {"name": "Семья", "target_per_month": 100}, {"name": "Друзья", "target_per_month": 1},
        {"name": "Пусто", "target_per_month": 0},
    ]})

    rec = st.recommend("life_balance", settings, [both], {})[both.id]

    assert rec.frequency_days == 7  # min(max(round(0.3), 7), 30)
    assert "Семья" in rec.reason


def test_custom_rules_pick_the_shortest_matching_frequency():
    c = view("Коллега", tags=("работа",), priority="top", group_ids=("g1",))
    other = view("Чужой")
    settings = validate_settings("custom", {"rules": [
        {"kind": "tag", "value": "Работа", "frequency_days": 60},
        {"kind": "priority", "value": "top", "frequency_days": 14},
        {"kind": "group", "value": "g1", "frequency_days": 30},
        {"kind": "life_area", "value": "хобби", "frequency_days": 5},
    ]})

    recs = st.recommend("custom", settings, [c, other], {})

    assert recs[c.id].frequency_days == 14
    assert other.id not in recs


def test_custom_circle_rule_uses_assignments():
    c = view()
    settings = validate_settings("custom", {"rules": [{"kind": "circle", "value": "2", "frequency_days": 21}]})

    assert st.recommend("custom", settings, [c], {c.id: {"circle": 2}})[c.id].frequency_days == 21
    assert st.recommend("custom", settings, [c], {c.id: {"circle": 3}}) == {}


def test_primary_wins_and_additional_fill_gaps():
    a, b = view("А"), view("Б")
    s = state("deep_relations", ["max_contacts"], assignments={a.id: {"circle": 1}})

    recs = st.effective_recommendations(s, [a, b])

    assert recs[a.id].approach == "deep_relations" and recs[a.id].frequency_days == 7
    assert recs[b.id].approach == "max_contacts"


def test_no_primary_means_no_recommendations():
    assert st.effective_recommendations(state(None), [view()]) == {}


def test_active_approaches_dedupes_and_orders():
    assert st.active_approaches({"primary": "custom", "enabled": ["custom", "life_balance", "bogus"]}) == [
        "custom", "life_balance",
    ]


# --- следующие шаги -----------------------------------------------------------------------------


def test_next_steps_sorted_by_how_overdue_and_limited():
    stale, mild, fine = view("Давно", last=ago(300)), view("Чуть", last=ago(130)), view("Свежий", last=ago(10))

    steps = st.next_steps(state("max_contacts"), [fine, mild, stale], NOW)

    assert [s["name"] for s in steps] == ["Давно", "Чуть"]
    assert steps[0]["days_overdue"] == 180 and steps[0]["days_since"] == 300
    assert "не общались 300 дн." in steps[0]["reason"]
    assert len(st.next_steps(state("max_contacts"), [view(f"К{i}") for i in range(30)], NOW)) == 10
    assert len(st.next_steps(state("max_contacts"), [view(f"К{i}") for i in range(30)], NOW, limit=3)) == 3


def test_next_steps_skip_snoozed_and_never_contacted_uses_creation():
    snoozed = view("Отложен", snoozed_until=date(2026, 11, 20))
    expired = view("Просрочен отсрочка", snoozed_until=date(2026, 11, 1))
    new = view("Новый", created=5)
    never = view("Никогда", created=200)

    steps = st.next_steps(state("max_contacts"), [snoozed, expired, new, never], NOW)

    names = [s["name"] for s in steps]
    assert "Отложен" not in names and "Новый" not in names
    assert {"Просрочен отсрочка", "Никогда"} <= set(names)
    assert next(s for s in steps if s["name"] == "Никогда")["days_since"] is None


def test_next_steps_empty_without_strategy():
    assert st.next_steps(state(None), [view()], NOW) == []


# --- применение ---------------------------------------------------------------------------------


def test_preview_skips_manual_unless_overwrite():
    manual = view("Вручную", frequency_days=30)
    empty = view("Пустой")
    same = view("Совпало", frequency_days=120)
    s = state("max_contacts")

    preview = st.preview_apply(s, [manual, empty, same])

    actions = {i["name"]: i["action"] for i in preview["items"]}
    assert actions == {"Вручную": "skipped_manual", "Пустой": "change", "Совпало": "same"}
    assert (preview["will_change"], preview["skipped_manual"], preview["unchanged"]) == (1, 1, 1)
    assert preview["by_frequency"] == [{"frequency_days": 120, "count": 1}]

    forced = st.preview_apply(s, [manual, empty, same], overwrite=True)
    assert forced["will_change"] == 2 and forced["skipped_manual"] == 0


def test_previously_applied_frequency_is_not_manual():
    c = view("Применён", frequency_days=90)
    s = state("max_contacts", applied={c.id: 90})

    preview = st.preview_apply(s, [c])

    assert preview["items"][0]["action"] == "change" and not preview["items"][0]["was_manual"]


# --- метрики ------------------------------------------------------------------------------------


def test_max_contacts_metrics():
    contacts = [
        view("Новый 1", created=3, company="Яндекс", city="Москва", last=ago(10)),
        view("Новый 2", created=2, company="Яндекс", city="Казань", last=ago(300)),
        view("Старый", created=300, company="Сбер", city="", last=None),
        view("Ещё", created=300),
    ]

    m = st.compute_metrics("max_contacts", default_settings()["max_contacts"], ctx(contacts))

    new = next(t for t in m["targets"] if t["key"] == "new_contacts")
    coverage = next(t for t in m["targets"] if t["key"] == "coverage")
    assert new["value"] == 2 and new["target"] == 8 and new["progress"] == 0.25
    assert m["coverage"] == {"touched": 1, "total": 4, "pct": 25.0, "window_days": 180}
    assert coverage["progress"] == pytest.approx(25 / 70, abs=0.001)
    assert m["diversity"] == {"companies": 2, "cities": 2}
    assert len(m["new_per_month"]) == 6 and m["new_per_month"][-1]["y"] == 2
    assert len(m["hints"]) == 2


def test_new_per_month_series_buckets_by_month():
    contacts = [view(created=3), view(created=40), view(created=41), view(created=2000)]

    series = st.new_contacts_series(contacts, NOW)

    assert [p["x"] for p in series][-2:] == ["2026-10", "2026-11"]
    assert [p["y"] for p in series][-3:] == [1, 1, 1] and sum(p["y"] for p in series) == 3


def test_deep_metrics_overflow_schedule_and_average():
    members = [view(f"К{i}", last=ago(10 if i < 2 else 3)) for i in range(7)]
    settings = validate_settings("deep_relations", {"circles": [
        {"capacity": 5, "frequency_days": 7}, {"capacity": 10, "frequency_days": 30},
        {"capacity": 35, "frequency_days": 90}, {"capacity": 100, "frequency_days": 365},
    ]})
    assignments = {c.id: {"circle": 1} for c in members}
    outsider = view("Вне круга")

    m = st.compute_metrics("deep_relations", settings, ctx([*members, outsider], assignments=assignments))

    c1 = m["circles"][0]
    assert (c1["count"], c1["overflow"], c1["on_schedule"], c1["overdue"]) == (7, 2, 5, 2)
    assert c1["on_schedule_pct"] == pytest.approx(71.4, abs=0.1)
    assert c1["avg_days_since"] == pytest.approx((2 * 10 + 5 * 3) / 7, abs=0.1)
    assert m["circles"][1]["count"] == 0 and m["circles"][1]["on_schedule_pct"] is None
    assert m["unassigned"] == 1
    assert any("переполнен" in h for h in m["hints"]) and any("не распределены" in h for h in m["hints"])


def test_life_metrics_counts_each_interaction_once_per_sphere():
    fam = view("Мама", life_areas=("семья",))
    both = view("Брат", life_areas=("семья", "друзья"))
    touches = [([fam.id, both.id], ago(5)), ([both.id], ago(10)), ([fam.id], ago(100))]
    settings = validate_settings("life_balance", {"spheres": [
        {"name": "Семья", "target_per_month": 2}, {"name": "Друзья", "target_per_month": 1},
        {"name": "Здоровье", "target_per_month": 4},
    ]})

    m = st.compute_metrics("life_balance", settings, ctx([fam, both], touches, period=30))

    by_name = {s["name"]: s for s in m["spheres"]}
    assert by_name["Семья"]["touches"] == 2 and by_name["Семья"]["pct_of_target"] == 100
    assert by_name["Друзья"]["touches"] == 2 and by_name["Друзья"]["pct_of_target"] == 200
    assert by_name["Здоровье"]["touches"] == 0 and by_name["Здоровье"]["contacts"] == 0
    assert {r["sphere"]: r["actual"] for r in m["radar"]}["Друзья"] == 150  # капируется для колеса
    assert m["radar_by_period"]["90"][0]["sphere"] == "Семья" and "30" in m["radar_by_period"]
    assert any("Друзья" in h and "перекос" in h for h in m["hints"])
    assert any("Здоровье" in h for h in m["hints"])
    assert by_name["Семья"]["share_target"] == pytest.approx(28.6, abs=0.1)


def test_life_metrics_period_changes_window():
    c = view(life_areas=("семья",))
    touches = [([c.id], ago(60))]
    settings = validate_settings("life_balance", {"spheres": [{"name": "Семья", "target_per_month": 1}]})

    short = st.compute_metrics("life_balance", settings, ctx([c], touches, period=30))
    long = st.compute_metrics("life_balance", settings, ctx([c], touches, period=90))

    assert short["spheres"][0]["touches"] == 0 and long["spheres"][0]["touches"] == 1
    assert long["spheres"][0]["per_month"] == pytest.approx(0.3, abs=0.05)


def test_custom_metrics_rules_and_monthly_targets():
    a = view("А", tags=("друг",), last=ago(5), created=2)
    b = view("Б", tags=("друг",), last=ago(100))
    settings = validate_settings("custom", {
        "rules": [{"kind": "tag", "value": "друг", "frequency_days": 30}, {"kind": "tag", "value": "нет", "frequency_days": 7}],
        "new_per_month": 2, "touches_per_month": 4,
    })
    touches = [([a.id], ago(3)), ([b.id], ago(20))]

    m = st.compute_metrics("custom", settings, ctx([a, b], touches, period=30))

    assert m["rules"][0]["count"] == 2 and m["rules"][0]["on_schedule"] == 1
    assert m["rules"][1]["count"] == 0 and any("ни один" in h for h in m["hints"])
    assert {t["key"]: t["value"] for t in m["targets"]} == {"new_contacts": 1.0, "touches": 2.0}


def test_compute_all_metrics_primary_first_and_progress_series():
    c = view(created=2)
    s = state("max_contacts", ["custom"])

    result = st.compute_all_metrics(s, ctx([c]))

    assert [a["id"] for a in result["approaches"]] == ["max_contacts", "custom"]
    series = st.goal_progress_series(result)
    assert series["approach"] == "Максимум контактов"
    assert [p["x"] for p in series["points"]] == ["Новых знакомств в этом месяце", "Сеть тронута за 180 дн."]
    assert st.goal_progress_series({"approaches": []}) == {"approach": None, "points": []}


def test_empty_database_metrics_do_not_crash():
    for approach in ("max_contacts", "deep_relations", "life_balance", "custom"):
        m = st.compute_metrics(approach, default_settings()[approach], ctx([]))
        assert m["id"] == approach


def test_contact_view_normalizes_document():
    doc = {
        "_id": ObjectId(), "first_name": "Анна", "last_name": "Ким", "priority": " High ", "tags": ["Друг", " "],
        "life_areas": ["Семья"], "keep_in_touch": {"frequency_days": 14, "snoozed_until": "2026-12-01"},
        "created_at": datetime(2026, 1, 1), "last_interaction_at": datetime(2026, 5, 1),
    }

    c = st.contact_view(doc, ago(3))

    assert c.name == "Анна Ким" and c.priority == "high" and c.tags == ("друг",) and c.life_areas == ("семья",)
    assert c.frequency_days == 14 and c.snoozed_until == date(2026, 12, 1)
    assert c.last_at == ago(3) and c.created_at.tzinfo is not None
