"""
PersonalCRM — FastAPI backend.
Точка входа: uvicorn app.main:app
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import ensure_legacy_admin
from .carddav import router as carddav_router
from .config import check_secrets, settings
from .db import close_db, connect_db, get_db
from .ratelimit import RateLimitMiddleware
from .storage import prepare_attachments_storage
from .repositories import contacts as contacts_repo
from .repositories import users as users_repo

logger = logging.getLogger(__name__)
from .routers import attachments as attachments_router
from .ai.jobs import close_assistant
from .routers import assistant as assistant_router
from .routers import assistant_chats as assistant_chats_router
from .routers import auth as auth_router
from .routers import calendar as calendar_router
from .routers import contacts as contacts_router
from .routers import groups as groups_router
from .routers import home as home_router
from .routers import interactions as interactions_router
from .routers import keep_in_touch as keep_in_touch_router
from .routers import network as network_router
from .routers import tags as tags_router
from .routers import questions as questions_router
from .routers import reminders as reminders_router
from .routers import templates as templates_router
from .routers import import_ as import_router
from .routers import sync as sync_router
from .routers import webhooks as webhooks_router


async def _backfill_phone_keys() -> None:
    """Разовая миграция: Phone.normalized для контактов всех пользователей."""
    from .sync.scheduler import user_dbs

    try:
        for db in await user_dbs():
            fixed = await contacts_repo.backfill_phone_keys(db)
            if fixed:
                logger.info("Ключи телефонов дописаны: %s контактов в %s", fixed, db.name)
    except Exception as exc:  # noqa: BLE001 — повторится при следующем старте
        logger.warning("Не удалось дописать ключи телефонов: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle-хук: MongoDB, пользователи, фоновый планировщик."""
    check_secrets(settings)
    await connect_db()
    try:
        await users_repo.ensure_indexes(get_db())
        await ensure_legacy_admin(get_db())
    except Exception as exc:  # noqa: BLE001 — без БД приложение всё равно стартует
        logger.warning("Не удалось подготовить коллекцию users: %s", exc)
    # Ключи телефонов у старых контактов — в фоне, старт не ждёт
    backfill_task = asyncio.create_task(_backfill_phone_keys())
    await prepare_attachments_storage()

    # Планировщик отключается в тестах (ENABLE_SCHEDULER=false), чтобы не
    # запускать фоновые задачи под TestClient.
    scheduler_on = os.getenv("ENABLE_SCHEDULER", "true").lower() != "false"
    if scheduler_on:
        try:
            from .sync.scheduler import start_scheduler

            start_scheduler()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось запустить планировщик: %s", exc)

    yield

    backfill_task.cancel()
    if scheduler_on:
        try:
            from .sync.scheduler import shutdown_scheduler

            shutdown_scheduler()
        except Exception:  # noqa: BLE001
            pass
    await close_assistant()
    await close_db()


app = FastAPI(
    title="PersonalCRM API",
    version="0.2.0",
    description="Персональная CRM с синхронизацией контактов",
    lifespan=lifespan,
)

# Рейт-лимиты на все запросы (добавлен раньше CORS — значит, CORS снаружи и 429 тоже с CORS-заголовками)
app.add_middleware(RateLimitMiddleware)

# CORS: разрешаем только наш фронтенд (FRONTEND_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url.rstrip("/")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Роутеры
# ---------------------------------------------------------------------------

# Auth: /api/auth/* — регистрация и вход публичные, остальное требует токена
app.include_router(auth_router.router)

# Contacts: /api/contacts/* — требуют токена
app.include_router(contacts_router.router)
# Вложения к контактам: /api/contacts/{id}/attachments (файлы — в S3 / MinIO)
app.include_router(attachments_router.router)

# Шаблоны карточек и вопросы к человеку (Sprint 5)
app.include_router(templates_router.router)
app.include_router(questions_router.router)
app.include_router(home_router.router)
app.include_router(reminders_router.router)

# Данные для экранов в стиле Dex (Sprint 11): группы, теги, лента взаимодействий, keep in touch, граф
app.include_router(groups_router.router)
app.include_router(tags_router.router)
app.include_router(interactions_router.router)
app.include_router(keep_in_touch_router.router)
app.include_router(network_router.router)

# Календарь: /api/calendar/* — события, привязанные к людям (Sprint 7)
app.include_router(calendar_router.router)

# Sync: /api/sync/* — подключение провайдеров и синхронизация (Sprint 2)
app.include_router(sync_router.router)

# Import: /api/import/* — загрузка файлов CSV/vCard/Telegram (Sprint 2)
app.include_router(import_router.router)

# Webhooks: /api/webhooks/* — публичные эндпоинты для уведомлений Microsoft (Sprint 3)
app.include_router(webhooks_router.router)

# CardDAV: /dav/* — контакты в iPhone / Android (Basic-auth: email + пароль для телефона)
app.include_router(carddav_router.router)

# ИИ-помощник: /api/assistant/* — задачи в очереди arq, модель — в отдельном воркере (Sprint 6)
app.include_router(assistant_router.router)
app.include_router(assistant_chats_router.router)


# ---------------------------------------------------------------------------
# Health-check (публичный)
# ---------------------------------------------------------------------------


@app.get("/api/health", tags=["system"])
async def health_check():
    """
    Проверка работоспособности сервиса и подключения к MongoDB.

    Возвращает:
    - status: "ok" если всё хорошо
    - db: "ok" / "error" — статус ping к MongoDB
    """
    db_status = "ok"
    db_error: str | None = None

    try:
        db = get_db()
        await db.client.admin.command("ping")
    except Exception as exc:
        db_status = "error"
        db_error = str(exc)

    return {
        "status": "ok",
        "db": db_status,
        **({"db_error": db_error} if db_error else {}),
    }
