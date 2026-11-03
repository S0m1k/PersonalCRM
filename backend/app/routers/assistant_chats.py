"""
Чаты помощника и досье контакта: /api/assistant/chats, /api/assistant/dossier.

Сообщение пользователя сохраняется сразу, ответ помощника — задача kind=chat в очереди:
клиент опрашивает GET /jobs/{id}, а готовый ответ читает из истории чата (тот же result.blocks).
Чаты лежат в базе пользователя, поэтому чужие недоступны: запрос чужого id — 404.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..ai.dossier import get_dossier
from ..ai.jobs import Assistant, get_assistant
from ..auth import get_current_user, get_user_db
from ..config import settings
from ..models.assistant import JobOut
from ..models.chat import (
    ChatCreate,
    ChatOut,
    ChatUpdate,
    DossierOut,
    MessageCreate,
    MessageOut,
    MessagePage,
)
from ..models.user import User
from ..repositories import chats as chats_repo
from ..repositories import contacts as contacts_repo
from .assistant import _submit

router = APIRouter(prefix="/api/assistant", tags=["assistant-chats"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]
AssistantDep = Annotated[Assistant, Depends(get_assistant)]

PAGE_MAX = 100


class SentMessage(MessageOut):
    """Ответ на отправку: сообщение пользователя уже сохранено, ответ помощника придёт задачей."""

    job: JobOut


async def _own_chat(db: AsyncIOMotorDatabase, chat_id: str) -> ChatOut:
    chat = await chats_repo.get_chat(db, chat_id)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Чат не найден")
    return chat


@router.get("/chats", response_model=list[ChatOut], summary="Чаты, новые сверху")
async def list_chats(
    _user: AuthDep,
    db: DbDep,
    q: str = Query("", max_length=100, description="Поиск по названию"),
    archived: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=PAGE_MAX),
) -> list[ChatOut]:
    return await chats_repo.list_chats(db, q=q, archived=archived, skip=skip, limit=limit)


@router.post("/chats", response_model=ChatOut, status_code=status.HTTP_201_CREATED, summary="Новый чат")
async def create_chat(data: ChatCreate, _user: AuthDep, db: DbDep) -> ChatOut:
    if await chats_repo.count_chats(db) >= settings.chat_max_per_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Не больше {settings.chat_max_per_user} чатов — удалите ненужные",
        )
    return await chats_repo.create_chat(db, data.title)


@router.patch("/chats/{chat_id}", response_model=ChatOut, summary="Переименовать или архивировать чат")
async def update_chat(chat_id: str, data: ChatUpdate, _user: AuthDep, db: DbDep) -> ChatOut:
    changes = data.model_dump(exclude_none=True)
    if not changes:
        return await _own_chat(db, chat_id)
    chat = await chats_repo.update_chat(db, chat_id, changes)
    if chat is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Чат не найден")
    return chat


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Удалить чат с сообщениями")
async def delete_chat(chat_id: str, _user: AuthDep, db: DbDep) -> Response:
    if not await chats_repo.delete_chat(db, chat_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Чат не найден")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/chats/{chat_id}/messages", response_model=MessagePage, summary="История чата")
async def get_messages(
    chat_id: str,
    _user: AuthDep,
    db: DbDep,
    limit: int = Query(50, ge=1, le=PAGE_MAX),
    before: Optional[str] = Query(None, description="id сообщения: вернуть более ранние"),
) -> MessagePage:
    await _own_chat(db, chat_id)
    items, has_more = await chats_repo.list_messages(db, chat_id, limit=limit, before=before)
    return MessagePage(items=items, has_more=has_more)


@router.post(
    "/chats/{chat_id}/messages",
    response_model=SentMessage,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Отправить сообщение: ответ придёт задачей",
)
async def send_message(
    chat_id: str, data: MessageCreate, user: AuthDep, db: DbDep, assistant: AssistantDep
) -> SentMessage:
    chat = await _own_chat(db, chat_id)
    count = await chats_repo.count_messages(db, chat_id)
    if count >= settings.chat_max_messages:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="В чате слишком много сообщений — начните новый"
        )
    message = await chats_repo.add_message(db, chat_id, "user", data.text)
    try:
        job = await _submit(assistant, user, "chat", {"chat_id": chat_id, "message_id": message.id})
    except HTTPException:
        await chats_repo.delete_message(db, message.id)  # в очередь не встало: сообщение не оставляем
        raise
    if count == 0 and chat.title == chats_repo.DEFAULT_TITLE:
        await chats_repo.update_chat(db, chat_id, {"title": chats_repo.title_from_text(data.text)})
    return SentMessage(**message.model_dump(), job=job)


@router.post(
    "/dossier/{contact_id}",
    response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Составить досье контакта (задача в очереди)",
)
async def start_dossier(contact_id: str, user: AuthDep, db: DbDep, assistant: AssistantDep) -> JobOut:
    if await contacts_repo.get_contact_by_id(db, contact_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Контакт не найден")
    return await _submit(assistant, user, "dossier", {"contact_id": contact_id})


@router.get("/dossier/{contact_id}", response_model=DossierOut, summary="Последнее досье контакта")
async def read_dossier(contact_id: str, _user: AuthDep, db: DbDep) -> DossierOut:
    dossier = await get_dossier(db, contact_id)
    if dossier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Досье ещё не составлено")
    return DossierOut(**dossier)
