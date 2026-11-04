"""
Цели и стратегии: настройки подходов, состояние пользователя (коллекция goals, один документ).

Настройки каждого подхода проверяются своей моделью (лишние поля запрещены), поэтому в базу
попадают только числа в разумных границах. Каталог подходов (тексты) — в services/strategy.py.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

ApproachId = Literal["max_contacts", "deep_relations", "life_balance", "custom"]
APPROACH_IDS: tuple[str, ...] = ("max_contacts", "deep_relations", "life_balance", "custom")

FREQ_MIN, FREQ_MAX = 1, 730
CIRCLES = (1, 2, 3, 4)
MAX_SPHERES = 12
MAX_RULES = 30


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaxContactsSettings(_Strict):
    new_per_month: int = Field(default=8, ge=0, le=100)
    frequency_days: int = Field(default=120, ge=30, le=365)
    coverage_target_pct: int = Field(default=70, ge=10, le=100)
    coverage_window_days: int = Field(default=180, ge=30, le=365)


class Circle(_Strict):
    capacity: int = Field(ge=1, le=1000)
    frequency_days: int = Field(ge=FREQ_MIN, le=FREQ_MAX)


class DeepRelationsSettings(_Strict):
    # Слои Данбара 5 / 15 / 50 / 150 накопительные, поэтому ёмкость каждого круга — «сколько в нём одном»
    circles: list[Circle] = Field(
        default_factory=lambda: [
            Circle(capacity=5, frequency_days=7),
            Circle(capacity=10, frequency_days=30),
            Circle(capacity=35, frequency_days=90),
            Circle(capacity=100, frequency_days=365),
        ],
        min_length=4,
        max_length=4,
    )


class Sphere(_Strict):
    name: str = Field(min_length=1, max_length=40)
    target_per_month: float = Field(default=2, ge=0, le=100)

    @field_validator("name", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


DEFAULT_SPHERES = [
    ("Семья", 8), ("Друзья", 6), ("Работа и карьера", 6), ("Здоровье", 2),
    ("Развитие", 3), ("Хобби и отдых", 3), ("Сообщество", 2),
]


class LifeBalanceSettings(_Strict):
    spheres: list[Sphere] = Field(
        default_factory=lambda: [Sphere(name=n, target_per_month=t) for n, t in DEFAULT_SPHERES],
        max_length=MAX_SPHERES,
    )

    @field_validator("spheres")
    @classmethod
    def _unique(cls, v: list[Sphere]) -> list[Sphere]:
        names = [s.name.casefold() for s in v]
        if len(set(names)) != len(names):
            raise ValueError("Названия сфер не должны повторяться")
        return v


class Rule(_Strict):
    kind: Literal["tag", "group", "priority", "life_area", "circle"]
    value: str = Field(min_length=1, max_length=100)
    frequency_days: int = Field(ge=FREQ_MIN, le=FREQ_MAX)

    @field_validator("value", mode="before")
    @classmethod
    def _strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class CustomSettings(_Strict):
    rules: list[Rule] = Field(default_factory=list, max_length=MAX_RULES)
    new_per_month: Optional[int] = Field(default=None, ge=0, le=100)
    touches_per_month: Optional[int] = Field(default=None, ge=0, le=1000)


SETTINGS_MODELS: dict[str, type[BaseModel]] = {
    "max_contacts": MaxContactsSettings,
    "deep_relations": DeepRelationsSettings,
    "life_balance": LifeBalanceSettings,
    "custom": CustomSettings,
}


def default_settings() -> dict[str, dict]:
    return {k: m().model_dump() for k, m in SETTINGS_MODELS.items()}


def validate_settings(approach: str, raw: Any) -> dict:
    """Настройки подхода → проверенный словарь с значениями по умолчанию; иначе ValueError/ValidationError."""
    model = SETTINGS_MODELS.get(approach)
    if model is None:
        raise ValueError(f"Неизвестный подход: {approach}")
    return model.model_validate(raw or {}).model_dump()


class GoalsUpdate(_Strict):
    primary: Optional[ApproachId] = None
    clear_primary: bool = False
    enabled: Optional[list[ApproachId]] = None
    settings: Optional[dict[ApproachId, dict]] = None


class AssignmentsUpdate(_Strict):
    # contact_id -> круг 1..4; null снимает назначение
    assignments: dict[str, Optional[int]] = Field(max_length=2000)

    @field_validator("assignments")
    @classmethod
    def _circles(cls, v: dict[str, Optional[int]]) -> dict[str, Optional[int]]:
        for cid, circle in v.items():
            if circle is not None and circle not in CIRCLES:
                raise ValueError(f"Круг для {cid}: от 1 до 4")
        return v


class ApplyBody(_Strict):
    overwrite: bool = False
