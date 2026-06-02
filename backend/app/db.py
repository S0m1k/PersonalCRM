"""
Асинхронный клиент MongoDB через motor.
Lifecycle (connect / close) подключается к FastAPI lifespan в main.py.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .config import settings

logger = logging.getLogger(__name__)

# Модуль-уровень: клиент и база инициализируются при старте lifespan
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect_db() -> None:
    """
    Инициализировать клиент MongoDB. Вызывается при старте приложения.

    Клиент создаётся всегда (соединение у motor ленивое). Если сервер
    недоступен — НЕ роняем приложение: логируем предупреждение, а реальный
    статус БД отдаёт /api/health. serverSelectionTimeoutMS держим коротким,
    чтобы health-check и первый запрос не висели по 30 секунд.
    """
    global _client, _db
    _client = AsyncIOMotorClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=3000,
    )
    _db = _client[settings.db_name]

    try:
        await _client.admin.command("ping")
        logger.info("MongoDB connected: %s", settings.db_name)
    except Exception as exc:
        logger.warning(
            "MongoDB недоступна при старте (%s). Приложение запущено, "
            "статус БД смотрите в /api/health.",
            exc,
        )


async def close_db() -> None:
    """Закрыть соединение с MongoDB. Вызывается при остановке приложения."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_db() -> AsyncIOMotorDatabase:
    """Dependency / accessor для получения объекта базы данных."""
    if _db is None:
        raise RuntimeError("База данных не инициализирована. Проверьте lifespan.")
    return _db
