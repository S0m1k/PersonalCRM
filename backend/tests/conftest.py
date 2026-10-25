"""
Общая настройка тестов.

Отключаем фоновый планировщик (APScheduler), чтобы он не стартовал под
TestClient (его задачи лезли бы в сеть/БД по интервалу).

Переменные окружения важнее backend/.env, поэтому здесь фиксируем тестовые
значения: тесты не должны зависеть от локального .env (настоящий пароль,
ключи Microsoft/Google и т.п.).

Клиент MongoDB подменяется in-memory mongomock ДО импорта приложения: lifespan
при старте создаёт коллекцию users, и без подмены записал бы её в настоящую
базу из настроек (например, в локальный docker на этом компьютере).

Рейт-лимиты в общих тестах выключены (десятки входов подряд), их проверяет
test_ratelimit.py.
"""

import os

os.environ.setdefault("ENABLE_SCHEDULER", "false")

_TEST_SETTINGS = {
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin-test-pass",
    "SECRET_KEY": "test-secret-key-0123456789abcdef0123456789abcdef",
    "MAX_USERS": "1000",
    "ADMIN_PASSWORD_HASH": "",
    "MS_CLIENT_ID": "",
    "MS_CLIENT_SECRET": "",
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "FRONTEND_URL": "http://localhost:3000",
    "SYNC_INTERVAL_MINUTES": "30",
    "CARDDAV_PASSWORD": "",
    "REDIS_URL": "",
    "RATE_LIMIT_ENABLED": "false",
    "TRUST_PROXY_HEADERS": "false",
    "REGISTRATION_OPEN": "true",
}
os.environ.update(_TEST_SETTINGS)

from mongomock_motor import AsyncMongoMockClient  # noqa: E402

import app.db as _db_module  # noqa: E402

_db_module.AsyncIOMotorClient = AsyncMongoMockClient

import pytest  # noqa: E402

from app.auth import reset_legacy_check  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_legacy_admin_check():
    """У каждого теста своя in-memory база — перенос первого пользователя проверяется заново."""
    reset_legacy_check()
    yield
