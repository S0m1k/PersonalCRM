"""
Календарь Microsoft Graph: чтение изменений через calendarView/delta и запись событий.

- Первая синхронизация — calendarView/delta за окно sync_window(), дальше по deltaLink.
  calendarView раскрывает повторяющиеся встречи в отдельные экземпляры.
- Время запрашиваем в UTC (Prefer: outlook.timezone="UTC").
- Участников НЕ отправляем в Outlook: иначе Outlook разошлёт приглашения от имени
  пользователя. Участники из Outlook только читаются (для привязки к людям).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from .calendar_common import (
    HTTP_TIMEOUT_S,
    check_response,
    html_to_text,
    iso_z,
    strip_questions_block,
    sync_window,
    valid_tz,
)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
PAGE_SIZE = 100
# Защита от бесконечной пагинации
MAX_PAGES = 200


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)


def _headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Prefer": f'outlook.timezone="UTC", odata.maxpagesize={PAGE_SIZE}',
    }


def _parse_dt(value: Optional[dict]) -> Optional[datetime]:
    """{"dateTime": "2026-10-25T10:00:00.0000000", "timeZone": "UTC"} → aware UTC."""
    raw = (value or {}).get("dateTime")
    if not raw:
        return None
    main, _, frac = raw.rstrip("Z").partition(".")
    parsed = datetime.fromisoformat(main)
    if frac:
        parsed = parsed.replace(microsecond=int(frac[:6].ljust(6, "0")))
    return parsed.replace(tzinfo=timezone.utc)


def map_graph_event(event: dict) -> dict:
    """Событие Graph → поля события CRM."""
    all_day = bool(event.get("isAllDay"))
    start = _parse_dt(event.get("start"))
    end = _parse_dt(event.get("end")) or start
    if all_day and start is not None:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = (end or start).replace(hour=0, minute=0, second=0, microsecond=0)

    attendees = []
    organizer = (event.get("organizer") or {}).get("emailAddress") or {}
    if organizer.get("address"):
        attendees.append({"email": organizer["address"], "name": organizer.get("name", ""), "response": "organizer"})
    for att in event.get("attendees") or []:
        addr = att.get("emailAddress") or {}
        if not addr.get("address"):
            continue
        if any(a["email"].lower() == addr["address"].lower() for a in attendees):
            continue
        attendees.append(
            {
                "email": addr["address"],
                "name": addr.get("name", ""),
                "response": (att.get("status") or {}).get("response", ""),
            }
        )

    body = event.get("body") or {}
    content = body.get("content") or ""
    description = html_to_text(content) if body.get("contentType") == "html" else content.strip()

    return {
        "title": event.get("subject") or "(без названия)",
        "start": start,
        "end": end,
        "all_day": all_day,
        "timezone": valid_tz(event.get("originalStartTimeZone")),
        "location": ((event.get("location") or {}).get("displayName") or "")[:500],
        "description": strip_questions_block(description)[:20_000],
        "attendees": attendees,
        "etag": event.get("@odata.etag") or event.get("changeKey"),
        "web_link": event.get("webLink") or "",
    }


async def list_changes(access_token: str, delta_link: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """
    Изменения календаря. Без delta_link — все события окна.
    Возвращает (изменения, новый deltaLink).
    """
    if delta_link:
        url, params = delta_link, None
    else:
        start, end = sync_window()
        url = f"{GRAPH_BASE}/me/calendarView/delta"
        params = {"startDateTime": iso_z(start), "endDateTime": iso_z(end)}

    changes: list[dict] = []
    next_delta: Optional[str] = None
    async with _http() as client:
        for _ in range(MAX_PAGES):
            resp = await client.get(url, headers=_headers(access_token), params=params)
            check_response(resp)
            data = resp.json()
            for item in data.get("value", []):
                if not item.get("id"):
                    continue
                if "@removed" in item:
                    changes.append({"action": "deleted", "external_id": item["id"]})
                elif item.get("isCancelled"):
                    changes.append({"action": "deleted", "external_id": item["id"]})
                else:
                    changes.append({"action": "upsert", "external_id": item["id"], "data": map_graph_event(item)})
            if data.get("@odata.nextLink"):
                url, params = data["@odata.nextLink"], None
                continue
            next_delta = data.get("@odata.deltaLink")
            break
    return changes, next_delta


def to_graph_body(event: dict, description: str) -> dict:
    """Поля события CRM → тело Graph (без участников, см. описание модуля)."""
    if event.get("all_day"):
        start = {"dateTime": event["start"].strftime("%Y-%m-%dT00:00:00"), "timeZone": "UTC"}
        end = {"dateTime": event["end"].strftime("%Y-%m-%dT00:00:00"), "timeZone": "UTC"}
    else:
        start = {"dateTime": event["start"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}
        end = {"dateTime": event["end"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}
    return {
        "subject": event.get("title", ""),
        "body": {"contentType": "text", "content": description},
        "start": start,
        "end": end,
        "isAllDay": bool(event.get("all_day")),
        "location": {"displayName": event.get("location", "")},
    }


async def create_event(access_token: str, event: dict, description: str) -> tuple[str, dict]:
    """Создать событие в Outlook. Возвращает (id, поля из ответа)."""
    async with _http() as client:
        resp = await client.post(
            f"{GRAPH_BASE}/me/events", headers=_headers(access_token), json=to_graph_body(event, description)
        )
    check_response(resp)
    data = resp.json()
    return data["id"], map_graph_event(data)


async def update_event(access_token: str, external_id: str, event: dict, description: str) -> dict:
    async with _http() as client:
        resp = await client.patch(
            f"{GRAPH_BASE}/me/events/{external_id}",
            headers=_headers(access_token),
            json=to_graph_body(event, description),
        )
    check_response(resp)
    return map_graph_event(resp.json())


async def delete_event(access_token: str, external_id: str) -> None:
    async with _http() as client:
        resp = await client.delete(f"{GRAPH_BASE}/me/events/{external_id}", headers=_headers(access_token))
    if resp.status_code == 404:
        return  # уже удалено в Outlook
    check_response(resp)
