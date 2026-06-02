"""
PersonalCRM — FastAPI backend.
Точка входа: uvicorn app.main:app
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import close_db, connect_db, get_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle-хук: подключаем и закрываем MongoDB вместе с приложением."""
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="PersonalCRM API",
    version="0.1.0",
    description="Персональная CRM с синхронизацией контактов",
    lifespan=lifespan,
)

# CORS: в продакшне заменить origins на реальный домен фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
