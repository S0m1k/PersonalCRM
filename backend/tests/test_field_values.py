"""
Проверка и нормализация значений типизированных полей карточки.
"""

from __future__ import annotations

import pytest

from app.models.template import FieldDef
from app.services.fields import FieldValidationError, validate_field_values

DEFS = [
    FieldDef(key="note", label="Заметка", type="text"),
    FieldDef(key="story", label="История", type="longtext"),
    FieldDef(key="met", label="Познакомились", type="date"),
    FieldDef(key="budget", label="Бюджет", type="number"),
    FieldDef(key="stage", label="Стадия", type="select", options=["Лид", "Клиент"]),
    FieldDef(key="site", label="Сайт", type="url"),
    FieldDef(key="vip", label="VIP", type="bool"),
]


def test_valid_values_are_normalized():
    result = validate_field_values(
        DEFS,
        {
            "note": "  привет ",
            "story": "много\nтекста",
            "met": "2024-03-01",
            "budget": "1500.5",
            "stage": "Клиент",
            "site": "example.com",
            "vip": "true",
        },
    )

    assert result == {
        "note": "привет",
        "story": "много\nтекста",
        "met": "2024-03-01",
        "budget": 1500.5,
        "stage": "Клиент",
        "site": "https://example.com",
        "vip": True,
    }


def test_integer_number_stays_integer():
    assert validate_field_values(DEFS, {"budget": 42})["budget"] == 42


def test_empty_values_are_dropped():
    assert validate_field_values(DEFS, {"note": "", "met": None, "budget": ""}) == {}


def test_unknown_keys_are_kept_as_is():
    """Поле удалили из шаблона — старое значение не теряем."""
    assert validate_field_values(DEFS, {"old_field": "значение"}) == {"old_field": "значение"}


@pytest.mark.parametrize(
    "key, value",
    [
        ("met", "01.03.2024"),
        ("met", "2024-02-30"),
        ("budget", "много"),
        ("stage", "Партнёр"),
        ("site", "not a url with spaces"),
        ("vip", "может быть"),
        ("note", "x" * 501),
    ],
)
def test_invalid_values_raise_with_field_label(key, value):
    with pytest.raises(FieldValidationError) as exc:
        validate_field_values(DEFS, {key: value})

    label = next(d.label for d in DEFS if d.key == key)
    assert label in str(exc.value)


def test_all_errors_reported_together():
    with pytest.raises(FieldValidationError) as exc:
        validate_field_values(DEFS, {"met": "вчера", "budget": "много"})

    assert len(exc.value.errors) == 2
