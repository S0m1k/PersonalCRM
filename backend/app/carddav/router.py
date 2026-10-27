"""
Роутер CardDAV: /.well-known/carddav и /dav/…

Структура, которую видит телефон:
  /dav/                          — корень (discovery)
  /dav/principal/                — «пользователь»
  /dav/addressbooks/             — домашняя папка адресных книг
  /dav/addressbooks/contacts/    — единственная книга «PersonalCRM» = все контакты CRM
  /dav/addressbooks/contacts/<name>.vcf — карточка

Вход — HTTP Basic: email пользователя + пароль для телефона (выпускается в настройках
аккаунта, POST /api/auth/carddav-password). Каждый видит только контакты своей базы.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import carddav_digest, get_current_user, tenant_db
from ..db import get_db
from ..models.user import User
from ..repositories import users as users_repo
from ..caldav import handlers as caldav
from . import store
from .xml import (
    CALDAV,
    CARD,
    CS,
    DAV,
    MultiStatus,
    address_data_types,
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

ROOT = "/dav/"
PRINCIPAL = "/dav/principal/"
HOME = "/dav/addressbooks/"
BOOK = "/dav/addressbooks/contacts/"
METHODS = ["OPTIONS", "PROPFIND", "REPORT", "GET", "HEAD", "PUT", "DELETE"]

router = APIRouter(tags=["carddav"], include_in_schema=False)


# ---------------------------------------------------------------------------
# Доступ
# ---------------------------------------------------------------------------


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": 'Basic realm="PersonalCRM", charset="UTF-8"'},
    )


async def _check_auth(
    request: Request, system_db: Annotated[AsyncIOMotorDatabase, Depends(get_db)]
) -> AsyncIOMotorDatabase:
    """HTTP Basic (email + пароль для телефона) → база этого пользователя."""
    scheme, _, encoded = request.headers.get("Authorization", "").partition(" ")
    try:
        login, _, password = base64.b64decode(encoded).decode().partition(":")
    except (binascii.Error, UnicodeDecodeError):
        login, password = "", ""
    if scheme.lower() != "basic" or not login or not password:
        raise _unauthorized()
    doc = await users_repo.get_auth_doc(system_db, login)
    secret = (doc or {}).get("carddav_secret") or ""
    # compare_digest и для несуществующего пользователя — одинаковое время ответа
    is_valid = secrets.compare_digest(carddav_digest(password), secret or "0" * 64)
    if doc is None or not secret or not is_valid:
        raise _unauthorized()
    return tenant_db(system_db, doc["db_name"])


# База пользователя, вошедшего по Basic-auth
DavDbDep = Annotated[AsyncIOMotorDatabase, Depends(_check_auth)]


# ---------------------------------------------------------------------------
# Свойства ресурсов
# ---------------------------------------------------------------------------


def _common() -> dict:
    return {
        q(DAV, "current-user-principal"): href(PRINCIPAL),
        q(DAV, "principal-URL"): href(PRINCIPAL),
        q(CARD, "addressbook-home-set"): href(HOME),
        q(CALDAV, "calendar-home-set"): href(caldav.CAL_HOME),
    }


def _collection_props(path: str) -> dict:
    is_principal = path == PRINCIPAL
    kinds = [q(DAV, "collection")] + ([q(DAV, "principal")] if is_principal else [])
    return {
        **_common(),
        q(DAV, "resourcetype"): children(*kinds),
        q(DAV, "displayname"): text("Контакты" if path == HOME else "PersonalCRM"),
    }


async def _book_props(db: AsyncIOMotorDatabase) -> dict:
    tag = await store.ctag(db)
    return {
        **_common(),
        q(DAV, "resourcetype"): children(q(DAV, "collection"), q(CARD, "addressbook")),
        q(DAV, "displayname"): text("PersonalCRM"),
        q(CS, "getctag"): text(tag),
        q(DAV, "owner"): href(PRINCIPAL),
        q(DAV, "current-user-privilege-set"): privileges(
            "read", "write", "write-content", "write-properties", "bind", "unbind", "read-current-user-privilege-set"
        ),
        q(DAV, "supported-report-set"): reports(q(CARD, "addressbook-multiget"), q(CARD, "addressbook-query")),
        q(CARD, "supported-address-data"): address_data_types(),
        q(CARD, "max-resource-size"): text("1048576"),
    }


def _card_props(card: store.Card, with_data: bool) -> dict:
    props = {
        q(DAV, "getetag"): text(card.etag),
        q(DAV, "getcontenttype"): text("text/vcard; charset=utf-8"),
        q(DAV, "resourcetype"): children(),
    }
    if with_data:
        props[q(CARD, "address-data")] = text(store.render(card))
    return props


def _multistatus(ms: MultiStatus) -> Response:
    return Response(ms.to_bytes(), status_code=207, media_type="application/xml; charset=utf-8")


def _segments(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


# ---------------------------------------------------------------------------
# Маршруты
# ---------------------------------------------------------------------------


@router.get("/api/carddav/status", include_in_schema=True, summary="Как подключить телефон (без пароля)")
async def carddav_status(user: Annotated[User, Depends(get_current_user)]) -> dict:
    return {"enabled": user.has_carddav_password, "username": user.email, "path": ROOT}


@router.api_route("/.well-known/carddav", methods=METHODS)
async def well_known() -> RedirectResponse:
    return RedirectResponse(ROOT, status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.api_route("/.well-known/caldav", methods=METHODS)
async def well_known_caldav() -> RedirectResponse:
    return RedirectResponse(ROOT, status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.api_route("/dav", methods=METHODS)
async def dav_no_slash() -> RedirectResponse:
    return RedirectResponse(ROOT, status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.api_route("/dav/{path:path}", methods=METHODS)
async def dav(path: str, request: Request, db: DavDbDep) -> Response:
    parts = _segments(path)
    method = request.method

    if method == "OPTIONS":
        return Response(
            status_code=200,
            headers={"DAV": "1, 3, addressbook, calendar-access", "Allow": ", ".join(METHODS)},
        )

    if parts and parts[0] == "calendars":
        return await caldav.handle(method, parts, request, db)

    if len(parts) == 3 and parts[:2] == ["addressbooks", "contacts"]:
        return await _card_request(method, parts[2], request, db)

    if method == "PROPFIND":
        return await _propfind_collection(parts, request, db)
    if method == "REPORT" and parts == ["addressbooks", "contacts"]:
        return await _report(request, db)
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)


async def _propfind_collection(parts: list[str], request: Request, db: AsyncIOMotorDatabase) -> Response:
    wanted = requested_props(await request.body())
    depth = request.headers.get("Depth", "0")
    ms = MultiStatus()

    if parts in ([], ["principal"]):
        path = ROOT if not parts else PRINCIPAL
        ms.add(path, _collection_props(path), wanted)
    elif parts == ["addressbooks"]:
        ms.add(HOME, _collection_props(HOME), wanted)
        if depth != "0":
            ms.add(BOOK, await _book_props(db), wanted)
    elif parts == ["addressbooks", "contacts"]:
        ms.add(BOOK, await _book_props(db), wanted)
        if depth != "0":
            with_data = bool(wanted) and q(CARD, "address-data") in wanted
            for card in await store.list_cards(db, with_data=with_data):
                ms.add(BOOK + card.name, _card_props(card, with_data), wanted)
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _multistatus(ms)


async def _report(request: Request, db: AsyncIOMotorDatabase) -> Response:
    body = await request.body()
    root = parse(body)
    if root is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некорректный XML")
    wanted = requested_props(body)
    ms = MultiStatus()

    if root.tag == q(CARD, "addressbook-multiget"):
        for item_href in multiget_hrefs(root):
            name = item_href.rstrip("/").rsplit("/", 1)[-1]
            card = await store.find(db, name) if item_href.startswith(BOOK) else None
            if card is None:
                ms.add_missing(item_href)
            else:
                ms.add(BOOK + card.name, _card_props(card, with_data=True), wanted)
    elif root.tag == q(CARD, "addressbook-query"):
        # Фильтры не поддерживаем — книга небольшая, клиент отфильтрует сам
        for card in await store.list_cards(db, with_data=True):
            ms.add(BOOK + card.name, _card_props(card, with_data=True), wanted)
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Отчёт не поддерживается")
    return _multistatus(ms)


def _precondition_failed(request: Request, card: Optional[store.Card]) -> bool:
    if_match = request.headers.get("If-Match")
    if_none_match = request.headers.get("If-None-Match")
    if if_none_match == "*" and card is not None:
        return True
    if if_match and if_match != "*" and (card is None or if_match != card.etag):
        return True
    return bool(if_match == "*" and card is None)


async def _card_request(method: str, name: str, request: Request, db: AsyncIOMotorDatabase) -> Response:
    if not store.is_valid_name(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    card = await store.find(db, name)

    if method in ("GET", "HEAD"):
        if card is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        body = store.render(card).encode() if method == "GET" else b""
        return Response(body, media_type="text/vcard; charset=utf-8", headers={"ETag": card.etag})

    if method == "PROPFIND":
        if card is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        wanted = requested_props(await request.body())
        ms = MultiStatus()
        ms.add(BOOK + card.name, _card_props(card, with_data=bool(wanted) and q(CARD, "address-data") in wanted), wanted)
        return _multistatus(ms)

    if _precondition_failed(request, card):
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED)

    if method == "PUT":
        return await _put(name, card, request, db)
    if method == "DELETE":
        if card is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await store.delete(db, card)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    raise HTTPException(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)


async def _put(name: str, card: Optional[store.Card], request: Request, db: AsyncIOMotorDatabase) -> Response:
    try:
        body = (await request.body()).decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается UTF-8") from None
    if "BEGIN:VCARD" not in body.upper():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ожидается vCard")
    try:
        if card is None:
            saved = await store.create(db, name, body)
            return Response(status_code=status.HTTP_201_CREATED, headers={"ETag": saved.etag, "Location": BOOK + name})
        saved = await store.update(db, card, body)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"ETag": saved.etag})
