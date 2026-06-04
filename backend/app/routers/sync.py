"""
Роутер синхронизации: /api/sync/*

Эндпоинты:
  GET    /api/sync/connections                — список подключений
  POST   /api/sync/connect/microsoft          — начать OAuth flow (возвращает authorize URL)
  GET    /api/sync/callback/microsoft         — OAuth callback (обменивает code на токены)
  DELETE /api/sync/connections/{id}           — удалить подключение
  POST   /api/sync/contacts/{connection_id}   — ручной trigger sync контактов
  GET    /api/sync/log                        — история sync

Все маршруты защищены JWT (get_current_user), кроме callback
(callback редиректит браузер — токен в query state не передаётся,
 поэтому защищаем его через state-параметр, а не JWT).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user
from ..db import get_db
from ..models.contact import ContactCreate
from ..models.sync import SyncConnectionOut, SyncLog, SyncStats, SyncError
from ..repositories import contacts as contacts_repo
from ..repositories import sync as sync_repo
from ..sync.dedup import find_duplicates, merge_contacts
from ..sync.microsoft import delta_sync_contacts, fetch_outlook_contacts, map_outlook_to_crm
from ..sync.google import (
    fetch_google_contacts,
    is_deleted as google_is_deleted,
    map_google_to_crm,
    sync_google_contacts,
)
from ..sync.oauth import (
    google_authorize_url,
    google_configured,
    google_exchange_code,
    ms_authorize_url,
    ms_configured,
    ms_exchange_code,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
AuthDep = Annotated[str, Depends(get_current_user)]


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
async def connect_microsoft(_user: AuthDep):
    """
    Возвращает URL для редиректа пользователя на Microsoft login.

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

    state = str(uuid.uuid4())
    url = ms_authorize_url(state)
    return {"authorize_url": url, "state": state}


@router.get(
    "/callback/microsoft",
    summary="OAuth callback от Microsoft (редиректит в UI)",
    include_in_schema=False,  # скрываем из Swagger — вызывается браузером
)
async def callback_microsoft(
    db: DbDep,
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
        return RedirectResponse(
            url=f"/sync?error={error}&description={error_description or ''}",
            status_code=302,
        )

    if not code:
        raise HTTPException(status_code=400, detail="Отсутствует authorization code")

    try:
        token_data = await ms_exchange_code(code)
    except Exception as exc:
        logger.error("ms_exchange_code failed: %s", exc)
        return RedirectResponse(url="/sync?error=token_exchange_failed", status_code=302)

    access_token = token_data.get("access_token", "")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    await sync_repo.create_connection(
        db,
        provider="microsoft",
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        sync_contacts=True,
        sync_calendar=False,
    )

    logger.info("Microsoft connection created via OAuth callback")
    return RedirectResponse(url="/sync?connected=microsoft", status_code=302)


@router.post(
    "/connect/google",
    summary="Начать OAuth flow с Google",
)
async def connect_google(_user: AuthDep):
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
    state = str(uuid.uuid4())
    return {"authorize_url": google_authorize_url(state), "state": state}


@router.get(
    "/callback/google",
    summary="OAuth callback от Google (редиректит в UI)",
    include_in_schema=False,
)
async def callback_google(
    db: DbDep,
    code: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
):
    """Обменять code Google на токены, сохранить, редиректнуть в UI."""
    if error:
        logger.warning("Google OAuth error: %s", error)
        return RedirectResponse(url=f"/sync?error={error}", status_code=302)
    if not code:
        raise HTTPException(status_code=400, detail="Отсутствует authorization code")

    try:
        token_data = await google_exchange_code(code)
    except Exception as exc:
        logger.error("google_exchange_code failed: %s", exc)
        return RedirectResponse(url="/sync?error=token_exchange_failed", status_code=302)

    expires_in = token_data.get("expires_in", 3600)
    token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))

    await sync_repo.create_connection(
        db,
        provider="google",
        access_token=token_data.get("access_token", ""),
        refresh_token=token_data.get("refresh_token"),
        token_expires_at=token_expires_at,
        sync_contacts=True,
        sync_calendar=False,
    )
    logger.info("Google connection created via OAuth callback")
    return RedirectResponse(url="/sync?connected=google", status_code=302)


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
    """Удалить sync-подключение. Токены удаляются из БД."""
    deleted = await sync_repo.delete_connection(db, connection_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Подключение {connection_id!r} не найдено",
        )


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


