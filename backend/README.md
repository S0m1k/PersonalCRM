# PersonalCRM — Backend

FastAPI + MongoDB (motor). Python 3.12+.

## Локальный запуск (venv)

```bash
# 1. Создать и активировать виртуальное окружение
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# 2. Установить зависимости
pip install -r requirements.txt

# 3. Скопировать конфиг
copy .env.example .env   # Windows
# cp .env.example .env   # Linux/macOS

# 4. Убедиться что MongoDB запущена локально (или через docker-compose)
# 5. Запустить сервер
uvicorn app.main:app --reload --port 8000
```

Сервер поднимется на http://localhost:8000.  
Интерактивная документация API: http://localhost:8000/docs  
Health-check: http://localhost:8000/api/health

## Запуск через Docker

```bash
# Из корня проекта (рядом с docker-compose.yml):
docker-compose up --build
```

Только backend (без compose):
```bash
cd backend
docker build -t personalcrm-backend .
docker run -p 8000:8000 --env-file .env personalcrm-backend
```

## Структура

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py      # точка входа FastAPI, lifespan, CORS
│   ├── config.py    # настройки через pydantic-settings
│   └── db.py        # motor-клиент, connect/close, get_db()
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

## Переменные окружения

| Переменная     | По умолчанию                    | Описание                          |
|----------------|---------------------------------|-----------------------------------|
| `MONGODB_URI`  | `mongodb://localhost:27017`     | Строка подключения к MongoDB      |
| `DB_NAME`      | `personalcrm`                   | Имя базы данных                   |
| `SECRET_KEY`   | `change-me-in-production`       | Ключ подписи JWT (Sprint 1+)      |
