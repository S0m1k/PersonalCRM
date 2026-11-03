"""
arq-воркер задач ИИ. Запуск: arq app.ai.worker.WorkerSettings (сервис ai-worker в docker-compose).

- max_jobs = AI_CONCURRENCY — столько запросов к модели одновременно (GPU 8 ГБ — 1).
  Воркер должен быть один: при нескольких репликах предел умножается.
- Задача несёт только свой id; владельца и вход берём из записи в Redis, базу пользователя —
  по его записи в системной базе (tenant_db), как планировщик синхронизации.
- Недоступная модель → повтор через RETRY_DELAY_S (до AI_JOB_MAX_TRIES), остальные ошибки — сразу failed.
- Каждая задача пишет трассу (trace.py): в result.trace — владельцу, одной строкой — в лог.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from arq import Retry, func
from arq.connections import RedisSettings
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from ..auth import tenant_db
from ..config import settings
from ..repositories import users as users_repo
from .ask import run_ask
from .capture import run_capture
from .chat import run_chat
from .dossier import run_dossier
from .jobs import RUN_JOB, JobStore
from .llm import LLMError, LLMProvider, LLMUnavailableError, build_provider
from .tools import ToolError
from .trace import TimedLLM, log_job

logger = logging.getLogger(__name__)

RETRY_DELAY_S = 10
# Запас arq поверх нашего таймаута: успеваем записать failed до того, как arq снимет задачу
ARQ_TIMEOUT_MARGIN_S = 30

Handler = Callable[[AsyncIOMotorDatabase, LLMProvider, dict], Awaitable[dict]]
HANDLERS: dict[str, Handler] = {"capture": run_capture, "ask": run_ask, "chat": run_chat, "dossier": run_dossier}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def process_job(
    store: JobStore,
    system_db: AsyncIOMotorDatabase,
    llm: LLMProvider,
    job_id: str,
    job_try: int = 1,
    max_tries: int = settings.ai_job_max_tries,
    timeout_s: float = settings.ai_job_timeout_s,
) -> str:
    """Выполнить задачу и записать результат. Возвращает итоговый статус."""
    record = await store.get(job_id)
    if record is None or record["status"] not in ("queued", "running"):
        if record is not None:
            await store.release(record["user_id"], job_id)
        return record["status"] if record else "missing"
    user_id = record["user_id"]
    retrying = False
    started = time.perf_counter()
    timed = TimedLLM(llm)
    status, error, result = "failed", "", None

    def _log() -> None:
        trace = {**((result or {}).get("trace") or {}), "llm": timed.calls}
        log_job(job_id, record["kind"], user_id, status, round((time.perf_counter() - started) * 1000), trace, error)

    try:
        user = await users_repo.get_user(system_db, user_id)
        handler = HANDLERS.get(record["kind"])
        if user is None or handler is None:
            await store.update(job_id, status="failed", error="Задача недействительна", finished_at=_now_iso())
            return "failed"
        await store.update(job_id, status="running", started_at=_now_iso())
        db = tenant_db(system_db, user.db_name)
        try:
            # job_id нужен чату: ответ помощника хранится с id задачи (предпросмотр применяется по нему)
            payload = {**record["input"], "job_id": job_id}
            result = await asyncio.wait_for(handler(db, timed, payload), timeout=timeout_s)
        except LLMUnavailableError as exc:
            if job_try < max_tries:
                retrying = True
                status, error = "retry", str(exc)
                await store.update(job_id, status="queued")
                logger.warning("Задача %s: модель недоступна (%s), повтор", job_id, exc)
                raise Retry(defer=RETRY_DELAY_S) from exc
            error = "Модель недоступна, попробуйте позже"
            await store.update(job_id, status="failed", error=error, finished_at=_now_iso())
            return "failed"
        except asyncio.TimeoutError:
            error = "Модель не успела ответить"
            await store.update(job_id, status="failed", error=error, finished_at=_now_iso())
            return "failed"
        except (LLMError, ToolError) as exc:
            error = str(exc)
            await store.update(job_id, status="failed", error=error, finished_at=_now_iso())
            return "failed"
        except Exception:  # noqa: BLE001 — подробности в лог, пользователю — общее сообщение
            logger.exception("Задача %s упала", job_id)
            error = "Внутренняя ошибка помощника"
            await store.update(job_id, status="failed", error=error, finished_at=_now_iso())
            return "failed"
        status = "done"
        result = {
            **result,
            "trace": {
                **(result.get("trace") or {}),
                "llm": timed.calls,
                "total_ms": round((time.perf_counter() - started) * 1000),
            },
        }
        await store.update(job_id, status="done", result=result, finished_at=_now_iso())
        return "done"
    finally:
        _log()
        if not retrying:
            await store.release(user_id, job_id)


async def run_ai_job(ctx: dict[str, Any], job_id: str) -> str:
    return await process_job(ctx["store"], ctx["system_db"], ctx["llm"], job_id, job_try=ctx.get("job_try", 1))


def _setup_logging() -> None:
    """arq настраивает только свой логгер: без этого INFO-строки приложения (трасса задач) теряются."""
    app_logger = logging.getLogger("app")
    app_logger.setLevel(settings.ai_log_level.upper())
    if not app_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
        app_logger.addHandler(handler)
        app_logger.propagate = False


async def startup(ctx: dict[str, Any]) -> None:
    _setup_logging()
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
    ctx["mongo"] = client
    ctx["system_db"] = client[settings.db_name]
    ctx["store"] = JobStore(ctx["redis"])
    ctx["llm"] = build_provider()
    logger.info("ИИ-воркер запущен: модель %s, параллельно %d", ctx["llm"].name, settings.ai_concurrency)


async def shutdown(ctx: dict[str, Any]) -> None:
    client = ctx.get("mongo")
    if client is not None:
        client.close()


class WorkerSettings:
    functions = [
        func(
            run_ai_job,
            name=RUN_JOB,
            timeout=settings.ai_job_timeout_s + ARQ_TIMEOUT_MARGIN_S,
            max_tries=settings.ai_job_max_tries,
        )
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(settings.redis_url or "redis://localhost:6379/0")
    max_jobs = settings.ai_concurrency
    keep_result = 60  # результат живёт в нашей записи ai:job:<id>, у arq — только для отладки
    max_tries = settings.ai_job_max_tries
