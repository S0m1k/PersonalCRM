"""
Pydantic-модели чатов ИИ-помощника и блоков ответа.

Блок — единица ответа помощника: текст, график, таблица, ссылки на контакты или
предпросмотр захвата. Данные графиков и таблиц берутся из инструментов аналитики,
а не из слов модели: числа всегда настоящие. Размеры ограничены (точки, строки).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

MESSAGE_MAX = 4000
TITLE_MAX = 120
MAX_POINTS = 100
MAX_ROWS = 200
MAX_SERIES = 6
MAX_CONTACTS = 100


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


# ---------------------------------------------------------------------------
# Блоки
# ---------------------------------------------------------------------------


class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class Point(BaseModel):
    x: Union[str, int, float]
    y: float


class Series(BaseModel):
    name: str = ""
    points: list[Point] = Field(default_factory=list)

    @field_validator("points")
    @classmethod
    def _cap(cls, value: list[Point]) -> list[Point]:
        return value[:MAX_POINTS]


class ChartBlock(BaseModel):
    type: Literal["chart"] = "chart"
    chart: Literal["bar", "line", "pie"]
    title: str = ""
    x_label: str = ""
    y_label: str = ""
    series: list[Series] = Field(default_factory=list)

    @field_validator("series")
    @classmethod
    def _cap(cls, value: list[Series]) -> list[Series]:
        return value[:MAX_SERIES]


class Column(BaseModel):
    key: str
    label: str


class TableBlock(BaseModel):
    type: Literal["table"] = "table"
    title: str = ""
    columns: list[Column]
    rows: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("rows")
    @classmethod
    def _cap(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return value[:MAX_ROWS]


class ContactRef(BaseModel):
    id: str
    name: str = ""


class ContactsBlock(BaseModel):
    type: Literal["contacts"] = "contacts"
    contact_ids: list[str] = Field(default_factory=list)
    # Имена для чипов-ссылок; id без имени (контакт удалён) фронт пропускает
    contacts: list[ContactRef] = Field(default_factory=list)

    @field_validator("contact_ids")
    @classmethod
    def _cap(cls, value: list[str]) -> list[str]:
        return value[:MAX_CONTACTS]


class ErrorBlock(BaseModel):
    """Помощник не смог ответить (модель недоступна, таймаут, ошибка) — видно в истории чата."""

    type: Literal["error"] = "error"
    text: str


class CapturePreviewBlock(BaseModel):
    type: Literal["capture_preview"] = "capture_preview"
    job_id: str
    # Результат захвата (предпросмотр) — тот же, что у POST /capture
    result: dict[str, Any]
    # Итог применения (ApplyResult) — заполняется после /jobs/{id}/apply
    applied: Optional[dict[str, Any]] = None


Block = Annotated[
    Union[TextBlock, ChartBlock, TableBlock, ContactsBlock, CapturePreviewBlock, ErrorBlock],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Чаты и сообщения
# ---------------------------------------------------------------------------


class ChatCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=TITLE_MAX)

    _clean = field_validator("title", mode="before")(_strip)


class ChatUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=TITLE_MAX)
    archived: Optional[bool] = None

    _clean = field_validator("title", mode="before")(_strip)


class ChatOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    archived: bool = False
    summary: str = ""
    summary_upto: int = 0


class MessageCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=MESSAGE_MAX)

    _clean = field_validator("text", mode="before")(_strip)


class MessageOut(BaseModel):
    id: str
    chat_id: str
    role: Literal["user", "assistant"]
    content: str
    blocks: list[Block] = Field(default_factory=list)
    job_id: Optional[str] = None
    created_at: str


class MessagePage(BaseModel):
    items: list[MessageOut]
    # Есть более ранние сообщения: следующий запрос — before=<id первого элемента>
    has_more: bool = False


class DossierOut(BaseModel):
    contact_id: str
    text: str
    generated_at: str
    model: str = ""
