"""
Вложения: имена файлов, Content-Disposition и удаление вместе с контактом.
"""

from __future__ import annotations

import logging
import mimetypes
import re
import unicodedata
from urllib.parse import quote

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..repositories import attachments as repo
from ..storage import get_storage, is_configured

logger = logging.getLogger(__name__)

MAX_FILE_NAME = 200
DEFAULT_FILE_NAME = "file"
# Управляющие символы и запрещённые в именах файлов Windows/macOS
_BAD_CHARS = re.compile(r'[\x00-\x1f\x7f<>:"/\\|?*]')
_CONTENT_TYPE = re.compile(r"^[a-z0-9][a-z0-9!#$&^_.+-]{0,63}/[a-z0-9][a-z0-9!#$&^_.+-]{0,126}$")
DEFAULT_CONTENT_TYPE = "application/octet-stream"


def safe_file_name(raw: str | None) -> str:
    """Имя файла без пути, управляющих и запрещённых символов, не длиннее MAX_FILE_NAME."""
    name = unicodedata.normalize("NFC", raw or "")
    name = re.split(r"[/\\]", name)[-1]
    name = _BAD_CHARS.sub("_", name).strip().strip(".").strip()
    if len(name) > MAX_FILE_NAME:
        stem, dot, ext = name.rpartition(".")
        if dot and 0 < len(ext) <= 16:
            name = f"{stem[: MAX_FILE_NAME - len(ext) - 1]}.{ext}"
        else:
            name = name[:MAX_FILE_NAME]
    return name or DEFAULT_FILE_NAME


def content_type_for(file_name: str, declared: str | None) -> str:
    """
    Тип файла только для показа в интерфейсе: заявленный клиентом (если похож на MIME-тип)
    или угаданный по расширению. При скачивании всё равно отдаётся application/octet-stream.
    """
    value = (declared or "").split(";")[0].strip().lower()
    if _CONTENT_TYPE.match(value) and value != DEFAULT_CONTENT_TYPE:
        return value
    return mimetypes.guess_type(file_name)[0] or DEFAULT_CONTENT_TYPE


def content_disposition(file_name: str) -> str:
    """attachment с ASCII-именем для старых клиентов и полным именем в filename* (RFC 6266)."""
    ascii_name = file_name.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "").strip()
    ascii_name = ascii_name or DEFAULT_FILE_NAME
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_name, safe='')}"


async def delete_for_contact(db: AsyncIOMotorDatabase, contact_id: str) -> None:
    """
    Удалить вложения удалённого контакта: метаданные и объекты в S3.
    Объекты, которые не удалось стереть (хранилище недоступно), остаются сиротами — пишем в лог.
    """
    keys = await repo.delete_for_contact(db, contact_id)
    if not keys:
        return
    if not is_configured():
        logger.warning("Хранилище не настроено: %d файлов контакта %s не удалены из S3", len(keys), contact_id)
        return
    try:
        failed = await get_storage().delete_many(keys)
    except Exception as exc:  # noqa: BLE001 — удаление контакта не должно падать из-за S3
        logger.error("Не удалось удалить файлы контакта %s из S3 (%d шт.): %s", contact_id, len(keys), exc)
        return
    if failed:
        logger.error("Не удалены из S3 файлы контакта %s: %s", contact_id, failed)
