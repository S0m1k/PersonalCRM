"""
Google Calendar (основной календарь primary): чтение изменений через syncToken и запись событий.

- Первая синхронизация — события начиная с sync_window()[0] (singleEvents=true:
  повторяющиеся встречи раскрыты), в конце Google отдаёт nextSyncToken.
- Дальше — только изменения по syncToken (с ним нельзя timeMin/timeMax). 410 — токен протух.
- Отменённые события приходят со status="cancelled" (showDeleted=true).
- Участников в Google не отправляем (иначе Google разошлёт приглашения), только читаем.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
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

CALENDAR_BASE = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
PAGE_SIZE = 250
MAX_PAGES = 200


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT_S)


def _headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def _parse_when(value: Optional[dict]) -> tuple[Optional[datetime], bool]:
    """{"dateTime": RFC3339} или {"date": "2026-10-25"} → (UTC, весь день?)."""
    value = value or {}
    if value.get("date"):
        return datetime.combine(date.fromisoformat(value["date"]), time.min, tzinfo=timezone.utc), True
    if value.get("dateTime"):
        parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc), False
    return None, False


def map_google_event(event: dict) -> dict:
    """Событие Google Calendar → поля события CRM."""
    start, all_day = _parse_when(event.get("start"))
    end, _ = _parse_when(event.get("end"))

    attendees = []
    organizer = event.get("organizer") or {}
    if organizer.get("email") and not organizer.get("self"):
        attendees.append(
            {"email": organizer["email"], "name": organizer.get("displayName", ""), "response": "organizer"}
        )
    for att in event.get("attendees") or []:
        if not att.get("email") or att.get("self") or att.get("resource"):
            continue
        if any(a["email"].lower() == att["email"].lower() for a in attendees):
            continue
        attendees.append(
            {"email": att["email"], "name": att.get("displayName", ""), "response": att.get("responseStatus", "")}
        )

    return {
        "title": event.get("summary") or "(без названия)",
        "start": start,
        "end": end or start,
        "all_day": all_day,
        "timezone": valid_tz((event.get("start") or {}).get("timeZone")),
        "location": (event.get("location") or "")[:500],
        "description": strip_questions_block(html_to_text(event.get("description") or ""))[:20_000],
        "attendees": attendees,
        "etag": event.get("etag"),
        "web_link": event.get("htmlLink") or "",
    }


async def list_changes(access_token: str, sync_token: Optional[str] = None) -> tuple[list[dict], Optional[str]]:
    """Изменения календаря. Без sync_token — все события окна. Возвращает (изменения, nextSyncToken)."""
    base: dict = {"singleEvents": "true", "showDeleted": "true", "maxResults": PAGE_SIZE}
    if sync_token:
        base["syncToken"] = sync_token
    else:
        base["timeMin"] = iso_z(sync_window()[0])

    changes: list[dict] = []
    next_token: Optional[str] = None
    page_token: Optional[str] = None
    async with _http() as client:
        for _ in range(MAX_PAGES):
            params = {**base, **({"pageToken": page_token} if page_token else {})}
            resp = await client.get(CALENDAR_BASE, headers=_headers(access_token), params=params)
            check_response(resp)
            data = resp.json()
            for item in data.get("items", []):
                if not item.get("id"):
                    continue
                if item.get("status") == "cancelled":
                    changes.append({"action": "deleted", "external_id": item["id"]})
                else:
                    changes.append({"action": "upsert", "external_id": item["id"], "data": map_google_event(item)})
            page_token = data.get("nextPageToken")
            if not page_token:
                next_token = data.get("nextSyncToken")
                break
    return changes, next_token


def to_google_body(event: dict, description: str) -> dict:
    """Поля события CRM → тело Google Calendar (без участников)."""
    if event.get("all_day"):
        start = {"date": event["start"].date().isoformat()}
        end = {"date": event["end"].date().isoformat()}
    else:
        tz = event.get("timezone") or "UTC"
        start = {"dateTime": event["start"].astimezone(timezone.utc).isoformat(), "timeZone": tz}
        end = {"dateTime": event["end"].astimezone(timezone.utc).isoformat(), "timeZone": tz}
    return {
        "summary": event.get("title", ""),
        "description": description,
        "location": event.get("location", ""),
        "start": start,
        "end": end,
    }


async def create_event(access_token: str, event: dict, description: str) -> tuple[str, dict]:
    async with _http() as client:
        resp = await client.post(CALENDAR_BASE, headers=_headers(access_token), json=to_google_body(event, description))
    check_response(resp)
    data = resp.json()
    return data["id"], map_google_event(data)


async def update_event(access_token: str, external_id: str, event: dict, description: str) -> dict:
    async with _http() as client:
        resp = await client.patch(
            f"{CALENDAR_BASE}/{external_id}", headers=_headers(access_token), json=to_google_body(event, description)
        )
    check_response(resp)
    return map_google_event(resp.json())


async def delete_event(access_token: str, external_id: str) -> None:
    async with _http() as client:
        resp = await client.delete(f"{CALENDAR_BASE}/{external_id}", headers=_headers(access_token))
    if resp.status_code in (404, 410):
        return  # уже удалено в Google
    check_response(resp)
