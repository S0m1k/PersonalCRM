"""
Вложения к контактам: /api/contacts/{id}/attachments — список, загрузка, скачивание, удаление.

- Файлы — в S3 (app/storage.py), метаданные — в коллекции attachments базы пользователя.
  Чужой контакт в чужой базе, поэтому другой пользователь получает 404 по тем же id.
- Скачивание идёт потоком через backend, а не по presigned-ссылке: MinIO наружу не открыт
  (на сервере есть только Caddy + Tailscale Funnel), и проверка доступа остаётся одной — JWT.
- Отдаём всегда attachment + application/octet-stream + nosniff: файл не откроется в браузере
  как страница нашего сайта, что бы ни заявил загрузивший его клиент.
- Лимиты: ATTACHMENT_MAX_MB на файл (большие тела отклоняются по Content-Length ещё
  до разбора multipart) и ATTACHMENTS_QUOTA_MB на пользователя.
"""

from __future__ import annotations

import logging
from typing import Annotated, Callable
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from motor.motor_asyncio import AsyncIOMotorDatabase
from starlette.responses import Response

from ..auth import get_current_user, get_user_db
from ..config import settings
from ..models.attachment import AttachmentOut, AttachmentUsage
from ..models.user import User
from ..repositories import attachments as repo
from ..repositories import contacts as contacts_repo
from ..services.attachments import content_disposition, content_type_for, safe_file_name
from ..storage import ObjectStorage, StorageUnavailable, get_storage

logger = logging.getLogger(__name__)

MB = 1024 * 1024
# Запас на заголовки multipart поверх размера самого файла
MULTIPART_OVERHEAD = 64 * 1024


def max_file_size() -> int:
    return settings.attachment_max_mb * MB


def quota() -> int:
    return settings.attachments_quota_mb * MB


class UploadLimitRoute(APIRoute):
    """Отклонить слишком большое тело по Content-Length до того, как FastAPI разберёт multipart на диск."""

    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def limited(request: Request) -> Response:
            if request.method == "POST":
                length = request.headers.get("content-length")
                if length is None or not length.isdigit():
                    return JSONResponse({"detail": "Нужен заголовок Content-Length"}, status_code=411)
                if int(length) > max_file_size() + MULTIPART_OVERHEAD:
                    return JSONResponse(
                        {"detail": f"Файл больше {settings.attachment_max_mb} МБ"}, status_code=413
                    )
            return await handler(request)

        return limited


router = APIRouter(tags=["attachments"], route_class=UploadLimitRoute)

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]


def _storage() -> ObjectStorage:
    try:
        return get_storage()
    except StorageUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None


StorageDep = Annotated[ObjectStorage, Depends(_storage)]


def _unavailable(exc: Exception) -> HTTPException:
    logger.error("Хранилище вложений не отвечает: %s", exc)
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Хранилище файлов временно недоступно. Попробуйте позже.",
    )


async def _require_contact(db: AsyncIOMotorDatabase, contact_id: str) -> None:
    if await contacts_repo.get_contact_by_id(db, contact_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Контакт {contact_id!r} не найден")


async def _require_attachment(db: AsyncIOMotorDatabase, contact_id: str, attachment_id: str) -> dict:
    doc = await repo.get(db, contact_id, attachment_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден")
    return doc


@router.get("/api/attachments/usage", response_model=AttachmentUsage, summary="Занятое вложениями место")
async def usage(db: DbDep, _user: AuthDep) -> AttachmentUsage:
    return AttachmentUsage(used=await repo.total_size(db), quota=quota(), max_file_size=max_file_size())


@router.get(
    "/api/contacts/{contact_id}/attachments",
    response_model=list[AttachmentOut],
    summary="Вложения контакта",
)
async def list_attachments(contact_id: str, db: DbDep, _user: AuthDep) -> list[AttachmentOut]:
    await _require_contact(db, contact_id)
    return [AttachmentOut.from_mongo(d) for d in await repo.list_for_contact(db, contact_id)]


@router.post(
    "/api/contacts/{contact_id}/attachments",
    response_model=AttachmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить файл",
)
async def upload_attachment(
    contact_id: str,
    db: DbDep,
    user: AuthDep,
    storage: StorageDep,
    file: UploadFile = File(...),
) -> AttachmentOut:
    await _require_contact(db, contact_id)
    size = file.size or 0
    if size == 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Файл пустой")
    if size > max_file_size():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Файл больше {settings.attachment_max_mb} МБ",
        )
    # Квота проверяется до загрузки; параллельные загрузки могут превысить её на один файл
    if await repo.total_size(db) + size > quota():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Не хватает места: на все файлы — {settings.attachments_quota_mb} МБ. Удалите ненужные.",
        )

    file_name = safe_file_name(file.filename)
    object_key = f"{user.id}/{contact_id}/{uuid4().hex}"
    await repo.ensure_indexes(db)
    try:
        await storage.ensure_ready()
        await storage.put(object_key, file.file)
    except Exception as exc:  # noqa: BLE001 — любые ошибки S3/сети → 503
        raise _unavailable(exc) from None

    try:
        doc = await repo.create(
            db,
            contact_id=contact_id,
            file_name=file_name,
            size=size,
            content_type=content_type_for(file_name, file.content_type),
            object_key=object_key,
        )
    except Exception:
        # Без метаданных объект никто не найдёт — не оставляем сироту
        await storage.delete(object_key)
        raise
    return AttachmentOut.from_mongo(doc)


@router.get("/api/contacts/{contact_id}/attachments/{attachment_id}", summary="Скачать файл")
async def download_attachment(
    contact_id: str,
    attachment_id: str,
    db: DbDep,
    _user: AuthDep,
    storage: StorageDep,
) -> StreamingResponse:
    doc = await _require_attachment(db, contact_id, attachment_id)
    try:
        chunks = await storage.stream(doc["object_key"])
    except Exception as exc:  # noqa: BLE001
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            logger.error("Нет объекта %s для вложения %s", doc["object_key"], attachment_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Файл не найден") from None
        raise _unavailable(exc) from None
    return StreamingResponse(
        chunks,
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(doc["size"]),
            "Content-Disposition": content_disposition(doc["file_name"]),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Cache-Control": "private, no-store",
        },
    )


@router.delete(
    "/api/contacts/{contact_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Удалить файл",
)
async def delete_attachment(
    contact_id: str,
    attachment_id: str,
    db: DbDep,
    _user: AuthDep,
    storage: StorageDep,
) -> None:
    doc = await _require_attachment(db, contact_id, attachment_id)
    try:
        await storage.delete(doc["object_key"])
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc) from None
    await repo.delete(db, doc["_id"])
