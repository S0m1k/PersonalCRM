"""
Инструменты аналитики: цифры из базы, проверка параметров, реестр для модели и MCP.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.ai import analytics
from app.ai.analytics import ANALYTICS_TOOLS, run_tool, tool_specs, validate_params
from app.ai.tools import ToolError

NOW = datetime.now(timezone.utc)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["analytics"]


async def _add(db, **doc) -> str:
    doc.setdefault("created_at", NOW)
    return str((await db["contacts"].insert_one(doc)).inserted_id)


def _points(output, series=0) -> dict:
    return {p["x"]: p["y"] for p in output.blocks[0]["series"][series]["points"]}


# --- реестр и проверка параметров -----------------------------------------------------------


def test_registry_describes_every_tool_with_json_schema():
    specs = tool_specs()

    assert {s["name"] for s in specs} == {
        "count_contacts_by", "interactions_over_time", "birthdays_by_month",
        "contacts_added_over_time", "top_contacts_by_interactions", "stale_contacts", "goal_progress",
        "find_contacts",
    }
    for spec in specs:
        assert spec["description"]
        assert spec["input_schema"]["type"] == "object"
        assert spec["input_schema"]["additionalProperties"] is False


@pytest.mark.parametrize(
    "name, params",
    [
        ("drop_database", {}),
        (None, {}),
        ("count_contacts_by", {}),  # нет обязательного field
        ("count_contacts_by", {"field": "password"}),
        ("count_contacts_by", {"field": "city", "evil": 1}),
        ("count_contacts_by", "city"),
        ("stale_contacts", {"days": 0}),
        ("stale_contacts", {"days": "много"}),
        ("stale_contacts", {"days": True}),
        ("stale_contacts", {"limit": 10_000}),
        ("interactions_over_time", {"period": "year"}),
        ("interactions_over_time", {"from": "вчера"}),
        ("interactions_over_time", {"from": "2026-05-01", "to": "2026-01-01"}),
        ("interactions_over_time", {"contact_id": "not-an-id"}),
    ],
)
async def test_invalid_tool_calls_are_rejected(db, name, params):
    with pytest.raises(ToolError):
        await run_tool(db, name, params)


def test_validate_params_fills_defaults_and_drops_empty():
    tool = ANALYTICS_TOOLS["stale_contacts"]

    assert validate_params(tool, {"days": 30, "limit": ""}) == {"days": 30, "limit": 20}
    assert validate_params(tool, None) == {"days": 90, "limit": 20}


async def test_unknown_contact_in_interactions_is_error(db):
    with pytest.raises(ToolError, match="не найден"):
        await run_tool(db, "interactions_over_time", {"contact_id": "0" * 24})


# --- count_contacts_by ----------------------------------------------------------------------


async def test_count_by_city_groups_case_insensitively_and_counts_unspecified(db):
    await _add(db, first_name="А", city="Москва")
    await _add(db, first_name="Б", city="москва")
    await _add(db, first_name="В", city="Дубай")
    await _add(db, first_name="Г", city="")

    out = await run_tool(db, "count_contacts_by", {"field": "city"})

    assert out.facts["total_contacts"] == 4
    assert out.facts["counts"] == [
        {"value": "Москва", "count": 2}, {"value": "Дубай", "count": 1}, {"value": "Не указано", "count": 1},
    ]
    chart = out.blocks[0]
    assert chart["type"] == "chart" and chart["chart"] == "bar"
    assert _points(out) == {"Москва": 2, "Дубай": 1, "Не указано": 1}


async def test_count_by_tags_counts_each_tag_and_pie_is_selectable(db):
    await _add(db, first_name="А", tags=["друг", "школа"])
    await _add(db, first_name="Б", tags=["друг"])
    await _add(db, first_name="В")  # поля tags ещё может не быть

    out = await run_tool(db, "count_contacts_by", {"field": "tags", "chart": "pie"})

    assert out.blocks[0]["chart"] == "pie"
    assert _points(out) == {"друг": 2, "школа": 1, "Не указано": 1}


async def test_count_by_group_resolves_names_and_survives_missing_collection(db):
    group = (await db["groups"].insert_one({"name": "Семья"})).inserted_id
    await _add(db, first_name="А", group_ids=[str(group)])
    await _add(db, first_name="Б", group_ids=[str(group), "0" * 24])
    await _add(db, first_name="В")

    out = await run_tool(db, "count_contacts_by", {"field": "group"})

    assert _points(out) == {"Семья": 2, "Не указано": 1}

    bare = AsyncMongoMockClient()["no_groups"]
    await _add(bare, first_name="Z", group_ids=["x"])
    assert (await run_tool(bare, "count_contacts_by", {"field": "group"})).facts["counts"] == [
        {"value": "Не указано", "count": 1}
    ]


async def test_count_by_collapses_long_tail_into_other(db):
    for i in range(analytics.TOP_GROUPS + 3):
        await _add(db, first_name=str(i), company=f"Компания {i:02d}")

    out = await run_tool(db, "count_contacts_by", {"field": "company"})

    values = [c["value"] for c in out.facts["counts"]]
    assert len(values) == analytics.TOP_GROUPS + 1 and values[-1] == "Другие"
    assert out.facts["counts"][-1]["count"] == 3


async def test_count_on_empty_database_has_no_chart(db):
    out = await run_tool(db, "count_contacts_by", {"field": "company"})

    assert out.facts["total_contacts"] == 0 and out.blocks == []


# --- birthdays / added over time ------------------------------------------------------------


async def test_birthdays_by_month(db):
    await _add(db, first_name="А", birthday="1990-03-14")
    await _add(db, first_name="Б", birthday="1985-03-02")
    await _add(db, first_name="В", birthday="--12-31")
    await _add(db, first_name="Г", birthday="мусор")
    await _add(db, first_name="Д")

    out = await run_tool(db, "birthdays_by_month")

    points = _points(out)
    assert points["Мар"] == 2 and points["Дек"] == 1 and points["Янв"] == 0 and len(points) == 12
    assert out.facts["total_with_birthday"] == 3


async def test_birthdays_without_data_has_note_and_no_chart(db):
    out = await run_tool(db, "birthdays_by_month")

    assert out.blocks == [] and "note" in out.facts


async def test_contacts_added_over_time_monthly(db):
    await _add(db, first_name="А", created_at=datetime(2026, 1, 15, tzinfo=timezone.utc))
    await _add(db, first_name="Б", created_at=datetime(2026, 1, 20, tzinfo=timezone.utc))
    await _add(db, first_name="В", created_at=datetime(2026, 3, 1, tzinfo=timezone.utc))
    await _add(db, first_name="Г", created_at=datetime(2020, 1, 1, tzinfo=timezone.utc))  # вне периода

    out = await run_tool(db, "contacts_added_over_time", {"period": "month", "from": "2026-01-01", "to": "2026-04-10"})

    assert _points(out) == {"2026-01": 2, "2026-02": 0, "2026-03": 1, "2026-04": 0}
    assert out.blocks[0]["chart"] == "line" and out.facts["total"] == 3


async def test_contacts_added_weekly_uses_monday_buckets(db):
    await _add(db, first_name="А", created_at=datetime(2026, 3, 4, tzinfo=timezone.utc))  # среда, неделя с 02.03

    out = await run_tool(db, "contacts_added_over_time", {"period": "week", "from": "2026-03-01", "to": "2026-03-15"})

    assert _points(out) == {"2026-02-23": 0, "2026-03-02": 1, "2026-03-09": 0}


def test_default_range_and_bucket_cap():
    start, end = analytics._range({"period": "month"}, today=date(2026, 5, 20))
    assert (start, end) == (date(2025, 6, 1), date(2026, 5, 20))
    assert len(analytics._bucket_keys("month", start, end)) == 12
    long = analytics._bucket_keys("week", date(2015, 1, 1), date(2026, 1, 1))
    assert len(long) == analytics.MAX_BUCKETS and long[-1] == "2025-12-29"


# --- interactions ---------------------------------------------------------------------------


async def test_interactions_over_time_combines_interactions_and_past_events(db):
    cid = await _add(db, first_name="Пётр")
    for day in ("2026-01-10", "2026-01-20", "2026-02-05"):
        await db["interactions"].insert_one(
            {"contact_ids": [cid], "kind": "meeting", "occurred_at": datetime.fromisoformat(day + "T10:00:00")}
        )
    await db["events"].insert_one({"title": "Кофе", "start": datetime(2026, 2, 7, tzinfo=timezone.utc), "contact_ids": [cid]})
    await db["events"].insert_one({"title": "Будущее", "start": NOW + timedelta(days=30), "contact_ids": [cid]})
    await db["events"].insert_one({"title": "Без людей", "start": datetime(2026, 2, 8, tzinfo=timezone.utc), "contact_ids": []})

    out = await run_tool(db, "interactions_over_time", {"period": "month", "from": "2026-01-01", "to": "2026-03-31"})

    assert _points(out, 0) == {"2026-01": 2, "2026-02": 1, "2026-03": 0}
    assert out.blocks[0]["series"][1]["name"] == "Встречи в календаре"
    assert _points(out, 1) == {"2026-01": 0, "2026-02": 1, "2026-03": 0}


async def test_interactions_filtered_by_contact(db):
    a, b = await _add(db, first_name="А"), await _add(db, first_name="Б")
    await db["interactions"].insert_one({"contact_ids": [a], "occurred_at": datetime(2026, 1, 3, tzinfo=timezone.utc)})
    await db["interactions"].insert_one({"contact_ids": [b], "occurred_at": datetime(2026, 1, 4, tzinfo=timezone.utc)})
    await db["interactions"].insert_one({"contact_ids": [a, b], "occurred_at": "2026-01-05T09:00:00Z"})

    out = await run_tool(db, "interactions_over_time", {"contact_id": a, "from": "2026-01-01", "to": "2026-01-31"})

    assert _points(out) == {"2026-01": 2}


async def test_interactions_without_collection_returns_empty_series(db):
    out = await run_tool(db, "interactions_over_time", {"period": "week"})

    assert out.blocks == [] and out.facts["series"] == [] and "note" in out.facts


async def test_top_contacts_by_interactions_and_fallback_to_events(db):
    a, b = await _add(db, first_name="Анна", last_name="Ив"), await _add(db, first_name="Борис")
    # без взаимодействий — считаем встречи календаря
    for _ in range(2):
        await db["events"].insert_one({"start": datetime(2026, 1, 1, tzinfo=timezone.utc), "contact_ids": [b]})
    out = await run_tool(db, "top_contacts_by_interactions", {"limit": 5})
    assert out.facts["source"] == "events" and out.facts["top"][0]["name"] == "Борис"

    for _ in range(3):
        await db["interactions"].insert_one({"contact_ids": [a, "ghost"], "occurred_at": NOW})
    out = await run_tool(db, "top_contacts_by_interactions", {"limit": 1})

    assert out.facts["source"] == "interactions"
    assert [t["name"] for t in out.facts["top"]] == ["Анна Ив"]  # id без контакта пропущен, limit соблюдён
    assert out.blocks[1] == {"type": "contacts", "contact_ids": [a], "contacts": [{"id": a, "name": "Анна Ив"}]}


async def test_top_contacts_without_data(db):
    out = await run_tool(db, "top_contacts_by_interactions")

    assert out.blocks == [] and "note" in out.facts


async def test_stale_contacts_lists_old_then_never_contacted(db):
    old, fresh, never = [await _add(db, first_name=n) for n in ("Давний", "Свежий", "Никогда")]
    await db["interactions"].insert_one({"contact_ids": [old], "occurred_at": NOW - timedelta(days=200)})
    await db["interactions"].insert_one({"contact_ids": [fresh], "occurred_at": NOW - timedelta(days=5)})
    # встреча из календаря тоже считается контактом
    await db["events"].insert_one({"start": NOW - timedelta(days=1), "contact_ids": [fresh]})

    out = await run_tool(db, "stale_contacts", {"days": 90})

    rows = out.blocks[0]["rows"]
    assert [r["name"] for r in rows] == ["Давний", "Никогда"]
    assert rows[0]["days"] in (200, 199) and rows[1]["last_contact"] == "никогда" and rows[1]["days"] is None
    assert out.blocks[1]["contact_ids"] == [old, never]
    assert out.facts["stale_total"] == 1 and out.facts["never_contacted_total"] == 1


async def test_stale_contacts_none_found(db):
    cid = await _add(db, first_name="А")
    await db["interactions"].insert_one({"contact_ids": [cid], "occurred_at": NOW})

    out = await run_tool(db, "stale_contacts", {"days": 30})

    assert out.blocks == [] and "note" in out.facts


def test_dt_parsing():
    assert analytics._dt("2026-01-02") == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert analytics._dt(date(2026, 1, 2)) == datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert analytics._dt("не дата") is None and analytics._dt(None) is None


async def test_goal_progress_without_strategy_has_note(db):
    out = await run_tool(db, "goal_progress", {})

    assert "note" in out.facts and out.blocks == []


async def test_goal_progress_returns_chart_for_primary_approach(db):
    await db["goals"].insert_one({"_id": "goals", "primary": "max_contacts", "enabled": []})
    await _add(db, first_name="Анна")

    out = await run_tool(db, "goal_progress", {"period": 90})

    assert out.facts["approach"] == "Максимум контактов" and out.facts["period_days"] == 90
    points = out.blocks[0]["series"][0]["points"]
    assert [p["x"] for p in points] == ["Новых знакомств в этом месяце", "Сеть тронута за 180 дн."]


async def test_goal_progress_rejects_bad_period(db):
    with pytest.raises(ToolError):
        await run_tool(db, "goal_progress", {"period": 5})


# --- find_contacts: «кто в Санкт-Петербурге» — список людей, а не график ----------------------------


async def _people(db) -> None:
    await _add(db, first_name="Алексей", last_name="Лебедев", city="Санкт-Петербург", company="Ozon",
               position="Аналитик", tags=["данные"])
    await _add(db, first_name="Виктория", last_name="Тарасова", city="Санкт-Петербург", company="VK",
               position="Редактор", tags=["медиа"])
    await _add(db, first_name="Анна", last_name="Смирнова", city="Москва", company="Яндекс",
               position="Продакт-менеджер", tags=["продукт", "ментор"])
    await _add(db, first_name="Иван", last_name="Павлов", city="Дубай", company="Тинькофф", tags=["инвестор"])


def _names(output) -> list[str]:
    return [c["name"] for c in output.facts["shown"]]


@pytest.mark.parametrize("value", ["Санкт-Петербург", "Санкт-Петербурге", "СПб", "спб", "Питер", "в Питере"])
async def test_find_by_city_matches_word_forms_and_abbreviations(db, value):
    await _people(db)

    out = await run_tool(db, "find_contacts", {"field": "city", "value": value})

    assert sorted(_names(out)) == ["Алексей Лебедев", "Виктория Тарасова"]
    assert out.facts["total_matches"] == 2


async def test_find_returns_names_table_and_contact_chips_not_a_chart(db):
    await _people(db)

    out = await run_tool(db, "find_contacts", {"field": "city", "value": "Москве"})

    assert _names(out) == ["Анна Смирнова"]
    assert [b["type"] for b in out.blocks] == ["table", "contacts"]
    row = out.blocks[0]["rows"][0]
    assert row["name"] == "Анна Смирнова" and row["company"] == "Яндекс"
    assert out.blocks[1]["contacts"][0]["name"] == "Анна Смирнова"


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("company", "яндекс", ["Анна Смирнова"]),
        ("position", "аналитик", ["Алексей Лебедев"]),
        ("tag", "МЕНТОР", ["Анна Смирнова"]),
        ("text", "Павлов", ["Иван Павлов"]),
    ],
)
async def test_find_by_other_fields(db, field, value, expected):
    await _people(db)

    out = await run_tool(db, "find_contacts", {"field": field, "value": value})

    assert _names(out) == expected


async def test_find_by_group_resolves_group_names(db):
    gid = str((await db["groups"].insert_one({"name": "Семья"})).inserted_id)
    await _add(db, first_name="Пётр", last_name="Орлов", group_ids=[gid])
    await _add(db, first_name="Глеб", last_name="Ковалёв", group_ids=[])

    out = await run_tool(db, "find_contacts", {"field": "group", "value": "Семья"})

    assert _names(out) == ["Пётр Орлов"]


async def test_find_with_no_match_says_so_and_has_no_blocks(db):
    await _people(db)

    out = await run_tool(db, "find_contacts", {"field": "city", "value": "Лиссабон"})

    assert out.facts["total_matches"] == 0 and out.facts["shown"] == []
    assert out.blocks == []


async def test_find_limit_caps_shown_but_reports_the_total(db):
    for i in range(7):
        await _add(db, first_name=f"Имя{i}", last_name="Москвич", city="Москва")

    out = await run_tool(db, "find_contacts", {"field": "city", "value": "Москва", "limit": 3})

    assert len(out.facts["shown"]) == 3
    assert out.facts["total_matches"] == 7


@pytest.mark.parametrize(
    "params",
    [{"field": "city"}, {"value": "Москва"}, {"field": "password", "value": "x"}, {"field": "city", "value": "x" * 300},
     {"field": "city", "value": "Москва", "limit": 0}],
)
async def test_find_rejects_bad_params(db, params):
    with pytest.raises(ToolError):
        await run_tool(db, "find_contacts", params)
