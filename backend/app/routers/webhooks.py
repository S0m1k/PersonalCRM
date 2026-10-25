"""
Роутер вебхуков от внешних сервисов: /api/webhooks/*

Microsoft Graph при изменении контактов шлёт POST на /api/webhooks/microsoft:
  1. При создании подписки — validation handshake: GET/POST с ?validationToken=...,
     нужно вернуть этот токен как text/plain в течение 10 секунд.
  2. При изменениях — POST с body {"value": [{clientState, subscriptionId, ...}]}.
     Мы используем clientState = connection_id, находим подключение и запускаем
     синхронизацию в фоне, сразу отвечая 202.

Эндпоинт ПУБЛИЧНЫЙ (Microsoft вызывает без нашего JWT). Защита — через clientState.

ВАЖНО: для работы вебхуков notificationUrl должен быть публичным HTTPS-адресом.
На localhost уведомления не приходят (нужен туннель/прод-домен).
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import PlainTextResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import parse_webhook_client_state, tenant_db
from ..db import get_db
from ..repositories import sync as sync_repo
from ..repositories import users as users_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]


async def _sync_connection_in_background(db: AsyncIOMotorDatabase, connection_id: str) -> None:
    """Фоновая синхронизация контактов по уведомлению вебхука."""
    # Импорт здесь, чтобы избежать циклического импорта с routers.sync
    from datetime import datetime, timezone

    from ..models.sync import SyncError, SyncStats
    from ..routers.sync import _run_microsoft_sync

    conn = await sync_repo.get_connection(db, connection_id)
    if conn is None or conn.provider != "microsoft":
        return

    started_at = datetime.now(timezone.utc)
    log_entry = await sync_repo.create_log(
        db, connection_id=connection_id, type="contacts", action="webhook", started_at=started_at
    )
    stats = SyncStats()
    errors: list[SyncError] = []
    try:
        access_token, _ = sync_repo.get_decrypted_tokens(conn)
        await _run_microsoft_sync(db, conn, access_token, stats, errors)
    except Exception as exc:  # noqa: BLE001
        logger.error("webhook sync failed for %s: %s", connection_id, exc)
        stats.errors += 1
        errors.append(SyncError(error=str(exc)))
    await sync_repo.update_log(
        db, log_entry.id, stats=stats, errors=errors, completed_at=datetime.now(timezone.utc)
    )


async def _resolve_client_state(
    system_db: AsyncIOMotorDatabase, client_state: object
) -> Optional[tuple[AsyncIOMotorDatabase, str]]:
    """
    Подписанный clientState → (база пользователя, id подключения).
    Неподписанные (в т.ч. подписки однопользовательской версии) игнорируются —
    их продлевать не нужно, достаточно переподписаться в интерфейсе.
    """
    parsed = parse_webhook_client_state(client_state)
    if parsed is None:
        return None
    user_id, connection_id = parsed
    user = await users_repo.get_user(system_db, user_id)
    if user is None:
        return None
    return tenant_db(system_db, user.db_name), connection_id


@router.post("/microsoft", include_in_schema=False)
async def microsoft_webhook(
    request: Request,
    db: DbDep,
    background: BackgroundTasks,
    validationToken: Optional[str] = None,
):
    """
    Обработчик уведомлений Microsoft Graph.

    - validation handshake: вернуть validationToken как text/plain.
    - уведомление: запустить sync в фоне, ответить 202.
    """
    # 1. Validation handshake
    if validationToken:
        return PlainTextResponse(content=validationToken, status_code=200)

    # 2. Уведомление об изменениях
    try:
        body = await request.json()
    except Exception:
        return Response(status_code=202)
    if not isinstance(body, dict) or not isinstance(body.get("value"), list):
        return Response(status_code=202)

    for item in body["value"]:
        if not isinstance(item, dict):
            continue
        target = await _resolve_client_state(db, item.get("clientState"))
        if target:
            background.add_task(_sync_connection_in_background, *target)

    # Microsoft ждёт быстрый 202
    return Response(status_code=202)
