"""
Общая настройка тестов.

Отключаем фоновый планировщик (APScheduler), чтобы он не стартовал под
TestClient (его задачи лезли бы в сеть/БД по интервалу).
"""

import os

os.environ.setdefault("ENABLE_SCHEDULER", "false")
