"""
Роутер ИИ-помощника: /api/assistant.

Запрос к модели — задача в очереди: POST возвращает 202 с id, клиент опрашивает
GET /jobs/{id}. Быстрый захват ничего не меняет сам: изменения записываются только
через POST /jobs/{id}/apply с выбранными пользователем пунктами предпросмотра.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..ai.capture import apply_plan
from ..ai.jobs import Assistant, JobKind, QueueFullError, get_assistant
from ..ai.tools import ToolError
from ..auth import get_current_user, get_user_db
from ..config import settings
from ..models.assistant import (
    ApplyRequest,
    ApplyResult,
    AskRequest,
    AssistantInfo,
    CaptureRequest,
    JobOut,
)
from ..models.user import User

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]
AssistantDep = Annotated[Assistant, Depends(get_assistant)]


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Задача не найдена")


async def _submit(assistant: Assistant, user: User, kind: JobKind, payload: dict) -> JobOut:
    try:
        record = await assistant.submit(user.id, kind, payload)
    except QueueFullError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"У вас уже {settings.ai_user_max_queued} запроса в очереди — дождитесь ответа",
            headers={"Retry-After": "10"},
        ) from None
    return JobOut.from_record(record, await assistant.queue.position(record["id"]))


async def _own_job(assistant: Assistant, user: User, job_id: str) -> dict:
    record = await assistant.store.get_for_user(job_id, user.id)
    if record is None:
        raise _not_found()
    if assistant.is_expired(record):
        record = await assistant.store.update(
            job_id, status="failed", error="Очередь перегружена, задача не дождалась модели — повторите"
        ) or record
        await assistant.store.release(user.id, job_id)
    return record


@router.get("/info", response_model=AssistantInfo, summary="Модель и лимиты помощника")
async def info(_user: AuthDep) -> AssistantInfo:
    return AssistantInfo(
        model=settings.llm_model,
        fallback=settings.anthropic_model if settings.llm_fallback == "claude" and settings.anthropic_api_key else None,
        concurrency=settings.ai_concurrency,
        max_queued=settings.ai_user_max_queued,
    )


@router.post("/capture", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED, summary="Быстрый захват")
async def capture(data: CaptureRequest, user: AuthDep, assistant: AssistantDep) -> JobOut:
    return await _submit(assistant, user, "capture", {"text": data.text, "force": data.force})


@router.post("/ask", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED, summary="Вопрос по базе")
async def ask(data: AskRequest, user: AuthDep, assistant: AssistantDep) -> JobOut:
    return await _submit(assistant, user, "ask", {"question": data.question})


@router.get("/jobs/{job_id}", response_model=JobOut, summary="Статус и результат задачи")
async def get_job(job_id: str, user: AuthDep, assistant: AssistantDep) -> JobOut:
    record = await _own_job(assistant, user, job_id)
    position = await assistant.queue.position(job_id) if record["status"] == "queued" else None
    return JobOut.from_record(record, position)


@router.delete("/jobs/{job_id}", response_model=JobOut, summary="Отменить задачу в очереди")
async def cancel_job(job_id: str, user: AuthDep, assistant: AssistantDep) -> JobOut:
    record = await _own_job(assistant, user, job_id)
    if record["status"] != "queued":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Задача уже не в очереди")
    updated = await assistant.store.update(job_id, status="cancelled")
    await assistant.store.release(user.id, job_id)
    return JobOut.from_record(updated or record)


@router.post("/jobs/{job_id}/apply", response_model=ApplyResult, summary="Применить предпросмотр захвата")
async def apply_job(
    job_id: str, data: ApplyRequest, user: AuthDep, db: DbDep, assistant: AssistantDep
) -> ApplyResult:
    record = await _own_job(assistant, user, job_id)
    if record["kind"] != "capture" or record["status"] != "done" or not record.get("result"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Нечего применять")
    if not await assistant.store.lock_apply(job_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Изменения уже применены")
    try:
        outcome = await apply_plan(db, record["result"], data.actions, data.contact_id)
    except ToolError as exc:
        await assistant.store.unlock_apply(job_id)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    await assistant.store.update(job_id, status="applied", applied=outcome)
    return ApplyResult(**outcome)
