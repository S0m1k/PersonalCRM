"""
Роутер календаря: /api/calendar/events (Sprint 7).

События лежат в базе пользователя. Событие из Outlook / Google (есть connection_id
и external_id) при изменении и удалении меняется и у провайдера; событие, созданное
в CRM, можно сразу или потом записать в календарь подключения (connection_id).
Синхронизация «провайдер → CRM» — POST /api/sync/calendar/{id} и фоновый планировщик.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from ..auth import get_current_user, get_user_db
from ..models.event import Attendee, EventCreate, EventOut, EventUpdate, as_utc, normalize_range
from ..models.sync import SyncConnection
from ..models.user import User
from ..repositories import events as repo
from ..repositories import interactions as interactions_repo
from ..repositories import sync as sync_repo
from ..sync.calendar import connection_for, delete_remote, push_event
from ..sync.calendar_common import CalendarAccessError
from ..sync.oauth import calendar_scope_granted

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

PROVIDER_NAMES = {"microsoft": "Outlook", "google": "Google"}
CONSENT_MESSAGE = (
    "Нет доступа к календарю {name}. Переподключите аккаунт в «Синхронизации» и разрешите доступ к календарю."
)


class PushRequest(BaseModel):
    # Для события только из CRM — в какой календарь записать; для события провайдера не нужен
    connection_id: Optional[str] = None


def _not_found(event_id: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Событие {event_id!r} не найдено")


def _consent_error(conn: SyncConnection) -> HTTPException:
    name = PROVIDER_NAMES.get(conn.provider, conn.provider)
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CONSENT_MESSAGE.format(name=name))


def _remote_error(conn: SyncConnection, exc: Exception) -> HTTPException:
    if isinstance(exc, CalendarAccessError):
        return _consent_error(conn)
    logger.error("calendar push to %s failed: %s", conn.provider, exc)
    name = PROVIDER_NAMES.get(conn.provider, conn.provider)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Не удалось записать в календарь {name}")


async def _writable_connection(db: AsyncIOMotorDatabase, connection_id: str) -> SyncConnection:
    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подключение не найдено")
    if not calendar_scope_granted(conn.provider, conn.scopes) or conn.calendar_needs_consent:
        raise _consent_error(conn)
    return conn


async def _checked_contacts(db: AsyncIOMotorDatabase, ids: list[str]) -> list[str]:
    found = await repo.existing_contact_ids(db, ids)
    if len(found) != len(set(ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден")
    return found


@router.get("/events", response_model=list[EventOut], summary="События за период")
async def list_events(
    db: DbDep,
    _user: AuthDep,
    start: Optional[datetime] = Query(default=None, description="Начало периода (ISO, с поясом)"),
    end: Optional[datetime] = Query(default=None, description="Конец периода (ISO, с поясом)"),
    contact_id: Optional[str] = Query(default=None, description="Только события с этим человеком"),
) -> list[EventOut]:
    if start and end and end <= start:
        raise HTTPException(status_code=422, detail="Конец периода раньше начала")
    return await repo.list_events(db, start=start, end=end, contact_id=contact_id)


@router.get("/events/{event_id}", response_model=EventOut, summary="Событие")
async def get_event(event_id: str, db: DbDep, _user: AuthDep) -> EventOut:
    doc = await repo.get_event_doc(db, event_id)
    if doc is None:
        raise _not_found(event_id)
    return await repo.to_out(db, doc)


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED, summary="Создать событие")
async def create_event(data: EventCreate, db: DbDep, _user: AuthDep) -> EventOut:
    conn = await _writable_connection(db, data.connection_id) if data.connection_id else None
    chosen = await _checked_contacts(db, data.contact_ids)
    auto = await repo.match_contacts(db, data.attendees)
    fields = data.model_dump(exclude={"connection_id", "contact_ids"})
    doc = await repo.insert_event(
        db, {**fields, "contact_ids": repo.combine_links(auto, chosen, []), "manual_contact_ids": chosen}
    )
    if conn is not None:
        try:
            synced = await push_event(db, conn, doc)
        except Exception as exc:  # noqa: BLE001
            await repo.delete_event(db, str(doc["_id"]))
            raise _remote_error(conn, exc) from exc
        doc = await repo.update_event_doc(db, str(doc["_id"]), synced) or doc
    await interactions_repo.recompute_last_interaction(db, doc.get("contact_ids") or [])
    return await repo.to_out(db, doc)


async def _apply_update(db: AsyncIOMotorDatabase, doc: dict, data: EventUpdate) -> dict:
    """Изменения документа по EventUpdate (без записи)."""
    sent = data.model_dump(exclude_unset=True)
    changes = {k: v for k, v in sent.items() if k in ("title", "location", "description", "push_questions")}
    if changes.get("description") is None:
        changes.pop("description", None)
    if changes.get("location") is None:
        changes.pop("location", None)

    if {"start", "end", "all_day", "timezone"} & sent.keys():
        all_day = data.all_day if data.all_day is not None else doc.get("all_day", False)
        tz_name = data.timezone or doc.get("timezone") or "UTC"
        old_start, old_end = as_utc(doc["start"]), as_utc(doc["end"])
        # Сдвинули только начало — длительность сохраняется
        keep_duration = data.start is not None and data.end is None and all_day == doc.get("all_day", False)
        end_in = data.end if data.end is not None else (None if data.start is not None else old_end)
        try:
            start, end = normalize_range(data.start or old_start, end_in, all_day, tz_name)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if keep_duration:
            end = start + (old_end - old_start)
        changes.update(start=start, end=end, all_day=all_day, timezone=tz_name)

    attendees = data.attendees if data.attendees is not None else [Attendee(**a) for a in doc.get("attendees") or []]
    if data.attendees is not None:
        changes["attendees"] = [a.model_dump() for a in attendees]
    if data.contact_ids is not None or data.attendees is not None:
        auto = await repo.match_contacts(db, attendees)
        if data.contact_ids is not None:
            chosen = await _checked_contacts(db, data.contact_ids)
            manual, excluded = repo.split_manual_choice(chosen, auto)
        else:
            manual, excluded = doc.get("manual_contact_ids") or [], doc.get("excluded_contact_ids") or []
        changes.update(
            contact_ids=repo.combine_links(auto, manual, excluded),
            manual_contact_ids=manual,
            excluded_contact_ids=excluded,
        )
    return changes


@router.patch("/events/{event_id}", response_model=EventOut, summary="Изменить событие")
async def update_event(event_id: str, data: EventUpdate, db: DbDep, _user: AuthDep) -> EventOut:
    doc = await repo.get_event_doc(db, event_id)
    if doc is None:
        raise _not_found(event_id)
    changes = await _apply_update(db, doc, data)
    conn = await connection_for(db, doc)
    if conn is not None:
        if not calendar_scope_granted(conn.provider, conn.scopes) or conn.calendar_needs_consent:
            raise _consent_error(conn)
        try:
            changes.update(await push_event(db, conn, {**doc, **changes}))
        except Exception as exc:  # noqa: BLE001
            raise _remote_error(conn, exc) from exc
    updated = await repo.update_event_doc(db, event_id, changes) if changes else doc
    final = updated or doc
    # last_interaction_at: событие могло сдвинуться или сменить участников
    await interactions_repo.recompute_last_interaction(
        db, [*(doc.get("contact_ids") or []), *(final.get("contact_ids") or [])]
    )
    return await repo.to_out(db, final)


@router.post("/events/{event_id}/push", response_model=EventOut, summary="Записать событие в календарь провайдера")
async def push_to_provider(event_id: str, body: PushRequest, db: DbDep, _user: AuthDep) -> EventOut:
    """
    Событие только из CRM — создать в календаре подключения connection_id.
    Событие провайдера — перезаписать там (например, обновить блок вопросов в описании).
    """
    doc = await repo.get_event_doc(db, event_id)
    if doc is None:
        raise _not_found(event_id)
    current = await connection_for(db, doc)
    if current is not None:
        conn = await _writable_connection(db, current.id)
    elif body.connection_id:
        conn = await _writable_connection(db, body.connection_id)
    else:
        raise HTTPException(status_code=422, detail="Укажите connection_id — в какой календарь записать событие")
    try:
        synced = await push_event(db, conn, doc)
    except Exception as exc:  # noqa: BLE001
        raise _remote_error(conn, exc) from exc
    return await repo.to_out(db, await repo.update_event_doc(db, event_id, synced) or doc)


@router.delete(
    "/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, summary="Удалить событие"
)
async def delete_event(event_id: str, db: DbDep, _user: AuthDep) -> None:
    """Удаляет и у провайдера, если событие оттуда."""
    doc = await repo.get_event_doc(db, event_id)
    if doc is None:
        raise _not_found(event_id)
    conn = await connection_for(db, doc)
    if conn is not None:
        if not calendar_scope_granted(conn.provider, conn.scopes) or conn.calendar_needs_consent:
            raise _consent_error(conn)
        try:
            await delete_remote(db, conn, doc)
        except Exception as exc:  # noqa: BLE001
            raise _remote_error(conn, exc) from exc
    await repo.delete_event(db, event_id)
    await interactions_repo.recompute_last_interaction(db, doc.get("contact_ids") or [])
