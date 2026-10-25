"""
Общее для синхронизации календарей Microsoft Graph и Google Calendar.

Движки (calendar_microsoft / calendar_google) отдают изменения в едином виде:
  {"action": "upsert", "external_id": ..., "data": {поля события}}
  {"action": "deleted", "external_id": ...}
HTTP-клиент создаётся через _http() в каждом движке — тесты подменяют его на httpx.MockTransport.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

HTTP_TIMEOUT_S = 20.0
# Окно первой синхронизации: месяц назад и полгода вперёд
PAST_DAYS = 30
FUTURE_DAYS = 180

# Блок вопросов в описании события у провайдера. При чтении обратно — отрезается
QUESTIONS_MARKER = "——— Вопросы из PersonalCRM ———"


class CalendarAccessError(Exception):
    """Провайдер отказал в доступе к календарю (нет прав в токене — нужно переподключение)."""


class SyncStateExpired(Exception):
    """delta-link / syncToken протух — нужна полная синхронизация."""


def check_response(resp: httpx.Response) -> None:
    if resp.status_code in (401, 403):
        raise CalendarAccessError(f"{resp.status_code}: {resp.text[:200]}")
    if resp.status_code == 410:
        raise SyncStateExpired(resp.text[:200])
    resp.raise_for_status()


def sync_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=PAST_DAYS), now + timedelta(days=FUTURE_DAYS)


def iso_z(value: datetime) -> str:
    """2026-10-25T10:00:00Z"""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def valid_tz(name: str | None) -> str:
    if not name:
        return "UTC"
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"
    return name


_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<\s*(br|/p|/div|/li)\s*/?\s*>", re.IGNORECASE)
_STYLE = re.compile(r"<(style|script)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)


def html_to_text(value: str) -> str:
    """Описание у провайдеров часто в HTML — храним простым текстом."""
    if "<" not in value:
        return value.strip()
    text = _STYLE.sub("", value)
    text = _BREAK.sub("\n", text)
    text = html.unescape(_TAG.sub("", text)).replace("\xa0", " ")
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def strip_questions_block(description: str) -> str:
    return description.split(QUESTIONS_MARKER, 1)[0].rstrip()


def with_questions_block(description: str, questions: list[tuple[str, str]]) -> str:
    """Описание + блок «имя: вопрос». Без вопросов — описание как есть."""
    base = strip_questions_block(description)
    if not questions:
        return base
    lines = "\n".join(f"• {name}: {text}" if name else f"• {text}" for name, text in questions)
    return f"{base}\n\n{QUESTIONS_MARKER}\n{lines}".lstrip()
