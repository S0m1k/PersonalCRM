"""
Задачи ИИ: запись о задаче в Redis + постановка в очередь arq.

Запись ai:job:<id> (JSON, живёт AI_RESULT_TTL_S) хранит владельца, вход, статус и результат.
API отдаёт её только владельцу: чужая задача неотличима от несуществующей (404).
Набор ai:user:<id>:active — задачи пользователя в очереди и в работе (не больше AI_USER_MAX_QUEUED).

Статусы: queued → running → done | failed; queued → cancelled; done → applied (захват применён).
Параллельность запросов к модели ограничивает сам воркер (max_jobs = AI_CONCURRENCY).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Protocol

from fastapi import HTTPException, status

from ..config import Settings, settings

logger = logging.getLogger(__name__)

JobKind = Literal["capture", "ask", "chat", "dossier"]
JobStatus = Literal["queued", "running", "done", "failed", "cancelled", "applied"]
ARQ_QUEUE = "arq:queue"
RUN_JOB = "run_ai_job"
# Запись «в работе» старше этого считается брошенной (упал воркер) и не занимает место в лимите
ACTIVE_GRACE_S = 120


class QueueFullError(Exception):
    """У пользователя уже максимум задач в очереди."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, redis: Any, s: Settings = settings) -> None:
        self._redis = redis
        self._s = s

    @staticmethod
    def _key(job_id: str) -> str:
        return f"ai:job:{job_id}"

    @staticmethod
    def _active_key(user_id: str) -> str:
        return f"ai:user:{user_id}:active"

    def _stale_after(self) -> int:
        return self._s.ai_queue_expires_s + self._s.ai_job_timeout_s * self._s.ai_job_max_tries + ACTIVE_GRACE_S

    async def create(self, user_id: str, kind: JobKind, payload: dict) -> dict:
        job_id = uuid.uuid4().hex
        active = self._active_key(user_id)
        now = time.time()
        await self._redis.zremrangebyscore(active, 0, now - self._stale_after())
        await self._redis.zadd(active, {job_id: now})
        await self._redis.expire(active, self._stale_after())
        if await self._redis.zcard(active) > self._s.ai_user_max_queued:
            await self._redis.zrem(active, job_id)
            raise QueueFullError
        record = {
            "id": job_id,
            "user_id": user_id,
            "kind": kind,
            "input": payload,
            "status": "queued",
            "created_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        await self._redis.set(self._key(job_id), json.dumps(record, ensure_ascii=False), ex=self._s.ai_result_ttl_s)
        return record

    async def get(self, job_id: str) -> Optional[dict]:
        raw = await self._redis.get(self._key(job_id))
        return json.loads(raw) if raw else None

    async def get_for_user(self, job_id: str, user_id: str) -> Optional[dict]:
        record = await self.get(job_id)
        return record if record and record.get("user_id") == user_id else None

    async def update(self, job_id: str, **changes: Any) -> Optional[dict]:
        record = await self.get(job_id)
        if record is None:
            return None
        updated = {**record, **changes}
        await self._redis.set(self._key(job_id), json.dumps(updated, ensure_ascii=False), keepttl=True)
        return updated

    async def release(self, user_id: str, job_id: str) -> None:
        await self._redis.zrem(self._active_key(user_id), job_id)

    async def lock_apply(self, job_id: str) -> bool:
        """Защита от двойного применения: True — этот запрос первый."""
        return bool(await self._redis.set(f"{self._key(job_id)}:apply", "1", nx=True, ex=self._s.ai_result_ttl_s))

    async def unlock_apply(self, job_id: str) -> None:
        await self._redis.delete(f"{self._key(job_id)}:apply")


class Enqueuer(Protocol):
    async def enqueue(self, job_id: str) -> None:
        ...

    async def position(self, job_id: str) -> Optional[int]:
        ...


class ArqEnqueuer:
    def __init__(self, pool: Any, s: Settings = settings) -> None:
        self._pool = pool
        self._s = s

    async def enqueue(self, job_id: str) -> None:
        await self._pool.enqueue_job(RUN_JOB, job_id, _job_id=job_id, _expires=self._s.ai_queue_expires_s)

    async def position(self, job_id: str) -> Optional[int]:
        """Место в очереди с 1 или None, если задача уже не в очереди."""
        rank = await self._pool.zrank(ARQ_QUEUE, job_id)
        return None if rank is None else rank + 1


@dataclass(frozen=True)
class Assistant:
    store: JobStore
    queue: Enqueuer

    async def submit(self, user_id: str, kind: JobKind, payload: dict) -> dict:
        record = await self.store.create(user_id, kind, payload)
        try:
            await self.queue.enqueue(record["id"])
        except Exception:
            await self.store.release(user_id, record["id"])
            await self.store.update(record["id"], status="failed", error="Не удалось поставить задачу в очередь")
            raise
        return record

    def is_expired(self, record: dict, s: Settings = settings) -> bool:
        """Задача так и не взята в работу: arq её уже выбросил (_expires)."""
        if record["status"] != "queued":
            return False
        created = datetime.fromisoformat(record["created_at"])
        return (datetime.now(timezone.utc) - created).total_seconds() > s.ai_queue_expires_s + 30


_assistant: Optional[Assistant] = None


async def get_assistant() -> Assistant:
    """Dependency: очередь на REDIS_URL. Без Redis ИИ выключен (503), остальная CRM работает."""
    global _assistant
    if _assistant is None:
        if not settings.redis_url:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Помощник недоступен: не настроена очередь (REDIS_URL)",
            )
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        _assistant = Assistant(store=JobStore(pool), queue=ArqEnqueuer(pool))
    return _assistant


async def close_assistant() -> None:
    global _assistant
    if _assistant is not None and isinstance(_assistant.queue, ArqEnqueuer):
        try:
            await _assistant.queue._pool.aclose()
        except Exception:  # noqa: BLE001 — при остановке не важно
            pass
    _assistant = None
