"""
Обработчики CalDAV под /dav/calendars/…; маршрут и вход (Basic) — общие с CardDAV, см. carddav/router.py.

  /dav/calendars/                  — домашняя папка календарей
  /dav/calendars/events/           — единственный календарь «PersonalCRM» = все события CRM
  /dav/calendars/events/<name>.ics — событие
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..carddav.xml import (
    CALDAV,
    CS,
    DAV,
    MultiStatus,
    PropValue,
    calendar_components,
    children,
    href,
    multiget_hrefs,
    parse,
    privileges,
    q,
    reports,
    requested_props,
    text,
)
from ..services.ical import IcalError
from . import store

CAL_HOME = "/dav/calendars/"
CAL = "/dav/calendars/events/"
PRINCIPAL = "/dav/principal/"

_TIME = re.compile(r"^(\d{8}T\d{6})Z?$")
READ_ONLY_DETAIL = (
    "Событие из Outlook / Google с телефона не меняется — правьте его в приложении календаря этого аккаунта или в CRM"
)


def _principal_props() -> dict[str, PropValue]:
    return {
        q(DAV, "current-user-principal"): href(PRINCIPAL),
        q(DAV, "principal-URL"): href(PRINCIPAL),
        q(CALDAV, "calendar-home-set"): href(CAL_HOME),
    }


def home_props() -> dict[str, PropValue]:
    return {
        **_principal_props(),
        q(DAV, "resourcetype"): children(q(DAV, "collection")),
        q(DAV, "displayname"): text("Календари"),
    }


async def calendar_props(db: AsyncIOMotorDatabase) -> dict[str, PropValue]:
    return {
        **_principal_props(),
        q(DAV, "resourcetype"): children(q(DAV, "collection"), q(CALDAV, "calendar")),
        q(DAV, "displayname"): text("PersonalCRM"),
        q(CS, "getctag"): text(await store.ctag(db)),
        q(DAV, "owner"): href(PRINCIPAL),
        q(DAV, "current-user-privilege-set"): privileges(
            "read", "write", "write-content", "write-properties", "bind", "unbind", "read-current-user-privilege-set"
        ),
        q(CALDAV, "supported-calendar-component-set"): calendar_components("VEVENT"),
        q(DAV, "supported-report-set"): reports(q(CALDAV, "calendar-query"), q(CALDAV, "calendar-multiget")),
        q(CALDAV, "max-resource-size"): text("1048576"),
    }


def _item_props(item: store.Item, with_data: bool) -> dict[str, PropValue]:
    props: dict[str, PropValue] = {
        q(DAV, "getetag"): text(item.etag),
        q(DAV, "getcontenttype"): text("text/calendar; charset=utf-8; component=vevent"),
        q(DAV, "resourcetype"): children(),
    }
    if with_data:
        props[q(CALDAV, "calendar-data")] = text(store.render(item))
    return props


def _multistatus(ms: MultiStatus) -> Response:
    return Response(ms.to_bytes(), status_code=207, media_type="application/xml; charset=utf-8")


def _wants_data(wanted: Optional[list[str]]) -> bool:
    return bool(wanted) and q(CALDAV, "calendar-data") in wanted


def _time_range(root: ET.Element) -> tuple[Optional[datetime], Optional[datetime]]:
    """Период из <c:time-range start=… end=…> запроса calendar-query."""
    node = root.find(f".//{q(CALDAV, 'time-range')}")
    if node is None:
        return None, None

    def parse_stamp(value: Optional[str]) -> Optional[datetime]:
        match = _TIME.match(value or "")
        return datetime.strptime(match.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc) if match else None

    start, end = parse_stamp(node.get("start")), parse_stamp(node.get("end"))
    if start is not None and end is not None:
        return start, end
    # Открытый период: ограничиваем «разумным» окном, чтобы запрос остался таким же дешёвым
    return (start or datetime(1970, 1, 1, tzinfo=timezone.utc)), (end or datetime(2100, 1, 1, tzinfo=timezone.utc))


async def handle(method: str, parts: list[str], request: Request, db: AsyncIOMotorDatabase) -> Response:
    """parts — путь после /dav/, первый элемент «calendars»."""
    if len(parts) == 3 and parts[1] == "events":
        return await _item_request(method, parts[2], request, db)
    if method == "PROPFIND" and parts == ["calendars"]:
        return await _propfind_home(request, db)
    if method == "PROPFIND" and parts == ["calendars", "events"]:
        return await _propfind_calendar(request, db)
    if method == "REPORT" and parts == ["calendars", "events"]:
        return await _report(request, db)
    # Метод не для коллекции — 405; пути, которых нет, — 404
    is_collection = parts in (["calendars"], ["calendars", "events"])
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED if is_collection else status.HTTP_404_NOT_FOUND
    )


async def _propfind_home(request: Request, db: AsyncIOMotorDatabase) -> Response:
    wanted = requested_props(await request.body())
    ms = MultiStatus()
    ms.add(CAL_HOME, home_props(), wanted)
    if request.headers.get("Depth", "0") != "0":
        ms.add(CAL, await calendar_props(db), wanted)
    return _multistatus(ms)


async def _propfind_calendar(request: Request, db: AsyncIOMotorDatabase) -> Response:
    wanted = requested_props(await request.body())
    ms = MultiStatus()
    ms.add(CAL, await calendar_props(db), wanted)
    if request.headers.get("Depth", "0") != "0":
        with_data = _wants_data(wanted)
        for item in await store.list_items(db):
            ms.add(CAL + item.name, _item_props(item, with_data), wanted)
    return _multistatus(ms)


async def _report(request: Request, db: AsyncIOMotorDatabase) -> Response:
    body = await request.body()
    root = parse(body)
    if root is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный XML")
    wanted = requested_props(body)
    ms = MultiStatus()

    if root.tag == q(CALDAV, "calendar-multiget"):
        for item_href in multiget_hrefs(root):
            name = item_href.rstrip("/").rsplit("/", 1)[-1]
            item = await store.find(db, name) if item_href.startswith(CAL) else None
            if item is None:
                ms.add_missing(item_href)
            else:
                ms.add(CAL + item.name, _item_props(item, with_data=True), wanted)
    elif root.tag == q(CALDAV, "calendar-query"):
        start, end = _time_range(root)
        for item in await store.list_items(db, start, end):
            ms.add(CAL + item.name, _item_props(item, with_data=_wants_data(wanted)), wanted)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отчёт не поддерживается")
    return _multistatus(ms)


def _precondition_failed(request: Request, item: Optional[store.Item]) -> bool:
    if_match = request.headers.get("If-Match")
    if request.headers.get("If-None-Match") == "*" and item is not None:
        return True
    if if_match and if_match != "*" and (item is None or if_match != item.etag):
        return True
    return bool(if_match == "*" and item is None)


async def _item_request(method: str, name: str, request: Request, db: AsyncIOMotorDatabase) -> Response:
    if not store.is_valid_name(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    item = await store.find(db, name)

    if method in ("GET", "HEAD"):
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        body = store.render(item).encode() if method == "GET" else b""
        return Response(body, media_type="text/calendar; charset=utf-8", headers={"ETag": item.etag})

    if method == "PROPFIND":
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        wanted = requested_props(await request.body())
        ms = MultiStatus()
        ms.add(CAL + item.name, _item_props(item, _wants_data(wanted)), wanted)
        return _multistatus(ms)

    if _precondition_failed(request, item):
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED)
    if item is not None and item.is_read_only and method in ("PUT", "DELETE"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=READ_ONLY_DETAIL)

    if method == "PUT":
        return await _put(name, item, request, db)
    if method == "DELETE":
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await store.delete(db, item)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)


async def _put(name: str, item: Optional[store.Item], request: Request, db: AsyncIOMotorDatabase) -> Response:
    try:
        body = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается UTF-8") from None
    if "BEGIN:VCALENDAR" not in body.upper():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается iCalendar")
    try:
        if item is None:
            saved = await store.create(db, name, body)
            return Response(status_code=status.HTTP_201_CREATED, headers={"ETag": saved.etag, "Location": CAL + name})
        saved = await store.update(db, item, body)
    except (IcalError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"ETag": saved.etag})
