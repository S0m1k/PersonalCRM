"""
Pydantic-модели ИИ-помощника: запросы и задачи очереди.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

CAPTURE_MAX = 2000
QUESTION_MAX = 500


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class CaptureRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=CAPTURE_MAX)

    _clean = field_validator("text", mode="before")(_strip)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=QUESTION_MAX)

    _clean = field_validator("question", mode="before")(_strip)


class ApplyRequest(BaseModel):
    actions: list[int] = Field(..., min_length=1, max_length=50)
    # Другая карточка из кандидатов (или любая своя); None — найденная моделью / новый контакт
    contact_id: Optional[str] = None


class JobOut(BaseModel):
    id: str
    kind: str
    status: str
    position: Optional[int] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

    @classmethod
    def from_record(cls, record: dict, position: Optional[int] = None) -> "JobOut":
        # Владельца и вход наружу не отдаём: вход есть в result
        return cls(
            **{k: record.get(k) for k in ("id", "kind", "status", "created_at", "started_at", "finished_at",
                                          "result", "error")},
            position=position,
        )


class ApplyResult(BaseModel):
    contact_id: str
    created_contact: Optional[dict[str, Any]] = None
    results: list[dict[str, Any]]


class AssistantInfo(BaseModel):
    model: str
    fallback: Optional[str] = None
    concurrency: int
    max_queued: int
