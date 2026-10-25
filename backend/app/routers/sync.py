"""
Роутер синхронизации: /api/sync/*

Эндпоинты:
  GET    /api/sync/connections                — список подключений
  POST   /api/sync/connect/microsoft          — начать OAuth flow (возвращает authorize URL)
  GET    /api/sync/callback/microsoft         — OAuth callback (обменивает code на токены)
  DELETE /api/sync/connections/{id}           — удалить подключение
  PATCH  /api/sync/connections/{id}           — что синхронизировать (контакты / календарь)
  POST   /api/sync/contacts/{connection_id}   — ручной trigger sync контактов
  POST   /api/sync/calendar/{connection_id}   — ручной trigger sync календаря (Sprint 7)
  GET    /api/sync/log                        — история sync

Все маршруты защищены JWT (get_current_user), кроме callback
(callback редиректит браузер — токен в query state не передаётся,
 поэтому защищаем его через state-параметр, а не JWT). State имеет вид
 «<id пользователя>.<uuid>»: по нему callback находит базу пользователя,
 а сам state хранится в этой базе и одноразовый.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db, tenant_db, webhook_client_state
from ..config import settings
from ..db import get_db
from ..models.contact import ContactCreate
from ..models.sync import SyncConnectionOut, SyncConnectionUpdate, SyncLog, SyncStats, SyncError
from ..models.user import User
from ..repositories import contacts as contacts_repo
from ..repositories import events as events_repo
from ..repositories import sync as sync_repo
from ..repositories import users as users_repo
from ..sync.calendar import run_calendar_sync
from ..sync.calendar_common import CalendarAccessError
from ..sync.dedup import find_duplicates, merge_contacts
from ..sync.microsoft import (
    create_contact_subscription,
    delete_contact_subscription,
    delta_sync_contacts,
    fetch_outlook_contacts,
    map_outlook_to_crm,
    push_contact_to_outlook,
)
from ..sync.google import (
    fetch_google_contacts,
    is_deleted as google_is_deleted,
    map_google_to_crm,
    push_contact_to_google,
    sync_google_contacts,
)
from ..sync.oauth import (
    calendar_scope_granted,
    google_authorize_url,
    google_configured,
    google_exchange_code,
    ms_authorize_url,
    ms_configured,
    ms_exchange_code,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
# Системная база — только для callback'ов без JWT (пользователя находим по state)
SystemDbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _ui_redirect(**params: str) -> RedirectResponse:
    """Вернуть браузер на страницу /sync фронтенда с параметрами результата."""
    url = f"{settings.frontend_url.rstrip('/')}/sync?{urlencode(params)}"
    return RedirectResponse(url=url, status_code=302)


def _new_state(user: User) -> str:
    return f"{user.id}.{uuid.uuid4()}"


async def _db_for_state(
    system_db: AsyncIOMotorDatabase, state: Optional[str]
) -> Optional[AsyncIOMotorDatabase]:
    """База пользователя, которому выдан state. Сам state проверяет consume_oauth_state."""
    user_id, sep, _ = (state or "").partition(".")
    if not sep:
        return None
    user = await users_repo.get_user(system_db, user_id)
    return tenant_db(system_db, user.db_name) if user else None


CALENDAR_CONSENT_MESSAGE = (
    "Нет доступа к календарю. Переподключите аккаунт в «Синхронизации» и разрешите доступ к календарю."
)


async def _reconnect_target(db: AsyncIOMotorDatabase, connection_id: Optional[str], provider: str) -> Optional[str]:
    """Проверить подключение, которое переподключают (новые права у того же аккаунта)."""
    if not connection_id:
        return None
    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None or conn.provider != provider:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    return conn.id


async def _save_oauth_connection(
    db: AsyncIOMotorDatabase, provider: str, token_data: dict, state_doc: dict
) -> None:
    """
    Сохранить токены после callback. Переподключение (в state есть connection_id) обновляет
    существующее подключение — настройки и история остаются, добавляются права.
    """
    expires_in = token_data.get("expires_in", 3600)
    scopes = token_data.get("scope") or None
    fields = {
        "access_token": token_data.get("access_token", ""),
        "token_expires_at": datetime.now(timezone.utc) + timedelta(seconds=int(expires_in)),
        "scopes": scopes,
    }
    has_calendar = calendar_scope_granted(provider, scopes)
    existing_id = state_doc.get("connection_id")
    if existing_id and await sync_repo.get_connection(db, existing_id) is not None:
        if token_data.get("refresh_token"):
            fields["refresh_token"] = token_data["refresh_token"]
        if has_calendar:
            fields["sync_calendar"] = True
        await sync_repo.update_connection(db, existing_id, **fields, calendar_needs_consent=False)
        return
    await sync_repo.create_connection(
        db,
        provider=provider,
        refresh_token=token_data.get("refresh_token"),
        sync_contacts=True,
        sync_calendar=has_calendar,
        **fields,
    )


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------


@router.get(
    "/connections",
    response_model=list[SyncConnectionOut],
    summary="Список подключённых провайдеров",
)
async def list_connections(db: DbDep, _user: AuthDep) -> list[SyncConnectionOut]:
    """Вернуть все настроенные sync-подключения (без токенов)."""
    conns = await sync_repo.list_connections(db)
    return [SyncConnectionOut.from_connection(c) for c in conns]


@router.post(
    "/connect/microsoft",
    summary="Начать OAuth flow с Microsoft",
)
async def connect_microsoft(
    db: DbDep,
    user: AuthDep,
    connection_id: Optional[str] = Query(default=None, description="Переподключить это подключение"),
):
    """
    Возвращает URL для редиректа пользователя на Microsoft login.
    С connection_id — переподключение (например, чтобы выдать доступ к календарю).

    Если MS_CLIENT_ID / MS_CLIENT_SECRET не заданы — возвращает 501
    с объяснением как зарегистрировать приложение в Azure AD.
    """
    if not ms_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Microsoft OAuth не настроен. Необходимо зарегистрировать приложение в Azure AD "
                "и задать MS_CLIENT_ID, MS_CLIENT_SECRET, MS_REDIRECT_URI в файле .env. "
                "Инструкция: https://docs.microsoft.com/azure/active-directory/develop/quickstart-register-app"
            ),
        )

    target = await _reconnect_target(db, connection_id, "microsoft")
    state = _new_state(user)
    await sync_repo.save_oauth_state(db, state, "microsoft", connection_id=target)
    url = ms_authorize_url(state)
    return {"authorize_url": url, "state": state}


@router.get(
    "/callback/microsoft",
    summary="OAuth callback от Microsoft (редиректит в UI)",
    include_in_schema=False,  # скрываем из Swagger — вызывается браузером
)
async def callback_microsoft(
    system_db: SystemDbDep,
    code: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    error_description: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
):
    """
    Microsoft возвращает сюда code (или error) после авторизации пользователя.
    Меняем code на токены, сохраняем зашифрованными, редиректим в UI.
    """
    if error:
        logger.warning("Microsoft OAuth error: %s — %s", error, error_description)
        return _ui_redirect(error=error, description=error_description or "")

    if not code:
        raise HTTPException(status_code=400, detail="Отсутствует authorization code")

    db = await _db_for_state(system_db, state)
    state_doc = await sync_repo.consume_oauth_state_doc(db, state, "microsoft") if db is not None else None
    if state_doc is None:
        logger.warning("Microsoft OAuth callback with invalid state")
        return _ui_redirect(error="invalid_state")

    try:
        token_data = await ms_exchange_code(code)
    except Exception as exc:
        logger.error("ms_exchange_code failed: %s", exc)
        return _ui_redirect(error="token_exchange_failed")

    await _save_oauth_connection(db, "microsoft", token_data, state_doc)
    logger.info("Microsoft connection created via OAuth callback")
    return _ui_redirect(connected="microsoft")


@router.post(
    "/connect/google",
    summary="Начать OAuth flow с Google",
)
async def connect_google(
    db: DbDep,
    user: AuthDep,
    connection_id: Optional[str] = Query(default=None, description="Переподключить это подключение"),
):
    """Вернуть URL для редиректа на Google login (или 501 если не настроено)."""
    if not google_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Google OAuth не настроен. Создайте OAuth-клиент в Google Cloud Console "
                "и задайте GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI в .env. "
                "Инструкция: https://console.cloud.google.com/apis/credentials"
            ),
        )
    target = await _reconnect_target(db, connection_id, "google")
    state = _new_state(user)
    await sync_repo.save_oauth_state(db, state, "google", connection_id=target)
    return {"authorize_url": google_authorize_url(state), "state": state}


@router.get(
    "/callback/google",
    summary="OAuth callback от Google (редиректит в UI)",
    include_in_schema=False,
)
async def callback_google(
    system_db: SystemDbDep,
    code: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
):
    """Обменять code Google на токены, сохранить, редиректнуть в UI."""
    if error:
        logger.warning("Google OAuth error: %s", error)
        return _ui_redirect(error=error)
    if not code:
        raise HTTPException(status_code=400, detail="Отсутствует authorization code")

    db = await _db_for_state(system_db, state)
    state_doc = await sync_repo.consume_oauth_state_doc(db, state, "google") if db is not None else None
    if state_doc is None:
        logger.warning("Google OAuth callback with invalid state")
        return _ui_redirect(error="invalid_state")

    try:
        token_data = await google_exchange_code(code)
    except Exception as exc:
        logger.error("google_exchange_code failed: %s", exc)
        return _ui_redirect(error="token_exchange_failed")

    await _save_oauth_connection(db, "google", token_data, state_doc)
    logger.info("Google connection created via OAuth callback")
    return _ui_redirect(connected="google")


@router.delete(
    "/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Удалить подключение",
)
async def delete_connection(
    connection_id: str,
    db: DbDep,
    _user: AuthDep,
) -> None:
    """Удалить sync-подключение. Токены удаляются из БД, события его календаря — тоже."""
    deleted = await sync_repo.delete_connection(db, connection_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Подключение {connection_id!r} не найдено",
        )
    await events_repo.delete_for_connection(db, connection_id)


@router.patch(
    "/connections/{connection_id}",
    response_model=SyncConnectionOut,
    summary="Что синхронизировать: контакты / календарь",
)
async def update_connection_settings(
    connection_id: str, data: SyncConnectionUpdate, db: DbDep, _user: AuthDep
) -> SyncConnectionOut:
    changes = data.model_dump(exclude_none=True)
    conn = (
        await sync_repo.update_connection(db, connection_id, **changes)
        if changes
        else await sync_repo.get_connection(db, connection_id)
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    return SyncConnectionOut.from_connection(conn)


# ---------------------------------------------------------------------------
# Trigger sync
# ---------------------------------------------------------------------------


@router.post(
    "/contacts/{connection_id}",
    response_model=SyncLog,
    summary="Запустить синхронизацию контактов вручную",
)
async def trigger_sync_contacts(
    connection_id: str,
    db: DbDep,
    _user: AuthDep,
) -> SyncLog:
    """
    Ручной trigger синхронизации контактов для указанного подключения.

    Алгоритм:
    1. Достаём соединение и расшифровываем токены.
    2. Если есть delta_link — инкрементальный sync, иначе — полный.
    3. Для каждого контакта: дедупликация против существующей базы.
       - auto_merge (score ≥ 90): обновляем существующий
       - suggest_merge (70–89): пока создаём как новый (UI в Sprint 3)
       - new: создаём новый
    4. Записываем sync_log.
    """
    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Подключение {connection_id!r} не найдено",
        )

    started_at = datetime.now(timezone.utc)

    # Создаём лог-запись (начало)
    log_entry = await sync_repo.create_log(
        db,
        connection_id=connection_id,
        type="contacts",
        action="full_sync" if not conn.contacts_delta_link else "delta_sync",
        started_at=started_at,
    )

    stats = SyncStats()
    errors: list[SyncError] = []

    try:
        access_token, _ = sync_repo.get_decrypted_tokens(conn)

        if conn.provider == "microsoft":
            await _run_microsoft_sync(db, conn, access_token, stats, errors)
        elif conn.provider == "google":
            await _run_google_sync(db, conn, access_token, stats, errors)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Провайдер {conn.provider!r} не поддерживается",
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Sync failed for connection %s: %s", connection_id, exc)
        stats.errors += 1
        errors.append(SyncError(contact_name="", error=str(exc)))

    # Обновляем лог
    log_entry = await sync_repo.update_log(
        db,
        log_entry.id,
        stats=stats,
        errors=errors,
        completed_at=datetime.now(timezone.utc),
    )

    return log_entry


@router.post(
    "/calendar/{connection_id}",
    response_model=SyncLog,
    summary="Запустить синхронизацию календаря вручную",
)
async def trigger_sync_calendar(connection_id: str, db: DbDep, _user: AuthDep) -> SyncLog:
    """
    Подтянуть изменения календаря Outlook / Google. 403 — у подключения нет прав на календарь:
    его нужно переподключить в «Синхронизации» (подключения до Sprint 7 их не запрашивали).
    """
    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    if conn.provider not in ("microsoft", "google"):
        raise HTTPException(status_code=400, detail=f"Провайдер {conn.provider!r} не поддерживается")
    if not calendar_scope_granted(conn.provider, conn.scopes) or conn.calendar_needs_consent:
        raise HTTPException(status_code=403, detail=CALENDAR_CONSENT_MESSAGE)

    log_entry = await sync_repo.create_log(
        db,
        connection_id=connection_id,
        type="calendar",
        action="delta_sync" if conn.calendar_sync_state else "full_sync",
    )
    stats, errors = SyncStats(), []
    try:
        await run_calendar_sync(db, conn, stats, errors)
    except CalendarAccessError:
        await sync_repo.update_log(db, log_entry.id, stats=stats, errors=[SyncError(error="Нет доступа к календарю")])
        raise HTTPException(status_code=403, detail=CALENDAR_CONSENT_MESSAGE)
    except Exception as exc:  # noqa: BLE001
        logger.error("Calendar sync failed for connection %s: %s", connection_id, exc)
        stats.errors += 1
        errors.append(SyncError(error=str(exc)))
    return await sync_repo.update_log(db, log_entry.id, stats=stats, errors=errors)


async def _upsert_mapped_contact(
    db: AsyncIOMotorDatabase,
    mapped: dict,
    existing_dicts: list[dict],
    stats: SyncStats,
    errors: list[SyncError],
) -> None:
    """
    Обработать один замапленный контакт: дедупликация → merge или create.
    Конфликты решаются стратегией last-write-wins (внешний источник дополняет
    существующий контакт через merge_contacts; пустые поля заполняются,
    непустые сохраняются у существующего).
    """
    from ..models.contact import ContactUpdate

    name = f"{mapped.get('first_name', '')} {mapped.get('last_name', '')}".strip()
    try:
        duplicates = find_duplicates(mapped, existing_dicts)
        if duplicates and duplicates[0]["action"] == "auto_merge":
            best = duplicates[0]["existing_contact"]
            merged_data = merge_contacts(best, mapped)
            update = ContactUpdate.model_validate(
                {k: v for k, v in merged_data.items() if k not in ("id", "created_at", "updated_at")}
            )
            await contacts_repo.update_contact(db, best["id"], update)
            # Обновляем кэш, чтобы последующие контакты видели изменения
            for i, e in enumerate(existing_dicts):
                if e.get("id") == best["id"]:
                    existing_dicts[i] = merged_data
                    break
            stats.merged += 1
        else:
            create_data = ContactCreate.model_validate(mapped)
            new_c = await contacts_repo.create_contact(db, create_data)
            existing_dicts.append(new_c.model_dump())
            stats.created += 1
    except Exception as exc:
        logger.warning("Ошибка при обработке контакта %r: %s", name, exc)
        stats.errors += 1
        errors.append(SyncError(contact_name=name, error=str(exc)))


async def _run_microsoft_sync(
    db: AsyncIOMotorDatabase,
    conn,
    access_token: str,
    stats: SyncStats,
    errors: list[SyncError],
) -> None:
    """Синхронизация Microsoft контактов (мутирует stats и errors)."""
    if conn.contacts_delta_link:
        changes, next_delta = await delta_sync_contacts(access_token, conn.contacts_delta_link)
        outlook_contacts = [c["data"] for c in changes if c.get("action") == "upsert"]
        # TODO Sprint 4: обработка deleted (changes с action="deleted")
    else:
        outlook_contacts = await fetch_outlook_contacts(access_token)
        _, next_delta = await delta_sync_contacts(access_token)

    existing = await contacts_repo.list_contacts(db, limit=5000)
    existing_dicts = [c.model_dump() for c in existing]

    for oc in outlook_contacts:
        await _upsert_mapped_contact(db, map_outlook_to_crm(oc), existing_dicts, stats, errors)

    await sync_repo.update_connection(
        db,
        conn.id,
        contacts_delta_link=next_delta or conn.contacts_delta_link,
        contacts_last_sync=datetime.now(timezone.utc),
    )


async def _run_google_sync(
    db: AsyncIOMotorDatabase,
    conn,
    access_token: str,
    stats: SyncStats,
    errors: list[SyncError],
) -> None:
    """Синхронизация Google контактов через syncToken (мутирует stats и errors)."""
    import httpx

    try:
        contacts, next_token = await sync_google_contacts(access_token, conn.contacts_sync_token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 410:
            # syncToken протух — полный resync
            logger.info("Google syncToken протух, делаем полный resync")
            contacts, next_token = await fetch_google_contacts(access_token)
        else:
            raise

    existing = await contacts_repo.list_contacts(db, limit=5000)
    existing_dicts = [c.model_dump() for c in existing]

    for gc in contacts:
        if google_is_deleted(gc):
            # TODO Sprint 4: удаление контакта при удалении в Google
            stats.skipped += 1
            continue
        await _upsert_mapped_contact(db, map_google_to_crm(gc), existing_dicts, stats, errors)

    await sync_repo.update_connection(
        db,
        conn.id,
        contacts_sync_token=next_token or conn.contacts_sync_token,
        contacts_last_sync=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Push CRM → внешний сервис (двусторонний sync)
# ---------------------------------------------------------------------------


@router.post(
    "/contacts/{connection_id}/push/{contact_id}",
    summary="Отправить контакт CRM во внешний сервис (Outlook/Google)",
)
async def push_contact(
    connection_id: str,
    contact_id: str,
    db: DbDep,
    _user: AuthDep,
):
    """
    Создать или обновить контакт во внешнем сервисе подключения.
    После создания сохраняет внешний ID в external_ids контакта.
    """
    from ..models.contact import ContactUpdate

    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")

    contact = await contacts_repo.get_contact_by_id(db, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Контакт не найден")

    access_token, _ = sync_repo.get_decrypted_tokens(conn)
    crm_dict = contact.model_dump()

    try:
        if conn.provider == "microsoft":
            external_id = await push_contact_to_outlook(access_token, crm_dict)
            field = "outlook"
        elif conn.provider == "google":
            external_id = await push_contact_to_google(access_token, crm_dict)
            field = "google"
        else:
            raise HTTPException(status_code=400, detail=f"Провайдер {conn.provider!r} не поддерживается")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("push_contact failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Ошибка при отправке во внешний сервис: {exc}")

    # Сохраняем внешний ID обратно в контакт
    if external_id:
        ext = dict(contact.external_ids.model_dump())
        ext[field] = external_id
        await contacts_repo.update_contact(db, contact_id, ContactUpdate(external_ids=ext))

    return {"status": "ok", "provider": conn.provider, "external_id": external_id}


# ---------------------------------------------------------------------------
# Webhooks: подписка на изменения (Microsoft)
# ---------------------------------------------------------------------------


@router.post(
    "/connections/{connection_id}/subscribe",
    summary="Подписаться на изменения контактов (Microsoft webhook)",
)
async def subscribe_webhook(connection_id: str, db: DbDep, user: AuthDep):
    """
    Создать Graph-подписку на изменения контактов.

    notificationUrl формируется из PUBLIC_BASE_URL — он ДОЛЖЕН быть публичным
    HTTPS-адресом, иначе Microsoft отклонит подписку (на localhost не работает).
    """
    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    if conn.provider != "microsoft":
        raise HTTPException(status_code=400, detail="Вебхуки поддерживаются только для Microsoft")

    notification_url = f"{settings.public_base_url.rstrip('/')}/api/webhooks/microsoft"
    if not notification_url.startswith("https://"):
        raise HTTPException(
            status_code=400,
            detail=(
                "Для вебхуков нужен публичный HTTPS-адрес. Задайте PUBLIC_BASE_URL "
                "(https://...) — на localhost уведомления Microsoft не приходят."
            ),
        )

    access_token, _ = sync_repo.get_decrypted_tokens(conn)
    try:
        sub = await create_contact_subscription(
            # Вебхук приходит без JWT: по подписанному clientState находим пользователя и подключение
            access_token, notification_url, client_state=webhook_client_state(user.id, connection_id)
        )
    except Exception as exc:
        logger.error("create subscription failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Не удалось создать подписку: {exc}")

    await sync_repo.update_connection(
        db,
        connection_id,
        webhook_subscription_id=sub.get("id"),
        webhook_expires_at=datetime.now(timezone.utc) + timedelta(days=2, hours=12),
    )
    return {"status": "ok", "subscription_id": sub.get("id")}


@router.post(
    "/connections/{connection_id}/unsubscribe",
    summary="Отписаться от изменений контактов",
)
async def unsubscribe_webhook(connection_id: str, db: DbDep, _user: AuthDep):
    """Удалить Graph-подписку, если есть."""
    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    if conn.webhook_subscription_id:
        access_token, _ = sync_repo.get_decrypted_tokens(conn)
        try:
            await delete_contact_subscription(access_token, conn.webhook_subscription_id)
        except Exception as exc:
            logger.warning("delete subscription failed: %s", exc)
        await sync_repo.update_connection(
            db, connection_id, webhook_subscription_id=None, webhook_expires_at=None
        )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Sync log
# ---------------------------------------------------------------------------


@router.get(
    "/log",
    response_model=list[SyncLog],
    summary="История синхронизаций",
)
async def get_sync_log(
    db: DbDep,
    _user: AuthDep,
    connection_id: Optional[str] = Query(default=None, description="Фильтр по connection_id"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[SyncLog]:
    """Вернуть историю sync-операций."""
    return await sync_repo.list_logs(db, connection_id=connection_id, limit=limit)


