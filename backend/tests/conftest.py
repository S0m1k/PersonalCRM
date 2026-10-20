"""
Общая настройка тестов.

Отключаем фоновый планировщик (APScheduler), чтобы он не стартовал под
TestClient (его задачи лезли бы в сеть/БД по интервалу).

Переменные окружения важнее backend/.env, поэтому здесь фиксируем тестовые
значения: тесты не должны зависеть от локального .env (настоящий пароль,
ключи Microsoft/Google и т.п.).
"""

import os

os.environ.setdefault("ENABLE_SCHEDULER", "false")

_TEST_SETTINGS = {
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin",
    "ADMIN_PASSWORD_HASH": "",
    "MS_CLIENT_ID": "",
    "MS_CLIENT_SECRET": "",
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "FRONTEND_URL": "http://localhost:3000",
    "SYNC_INTERVAL_MINUTES": "30",
}
os.environ.update(_TEST_SETTINGS)
