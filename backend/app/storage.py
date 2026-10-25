"""
Объектное хранилище вложений: любой S3-совместимый сервис (MinIO в docker compose, AWS, Yandex …).

- boto3 синхронный — каждый вызов идёт через asyncio.to_thread, чтобы не блокировать event loop.
- Ключи объектов: <id пользователя>/<id контакта>/<случайный id> — файлы разных пользователей
  не пересекаются, имя файла в ключ не попадает (оно хранится в MongoDB).
- Объекты кладутся как application/octet-stream: тип от клиента для отдачи не используется.
- Bucket создаётся при старте backend (ensure_bucket), если его ещё нет.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from typing import BinaryIO, Optional

from .config import settings

logger = logging.getLogger(__name__)

CHUNK_SIZE = 256 * 1024
# delete_objects принимает не больше 1000 ключей за запрос
DELETE_BATCH = 1000
STORED_CONTENT_TYPE = "application/octet-stream"


class StorageUnavailable(RuntimeError):
    """Хранилище не настроено или не отвечает."""


class ObjectStorage:
    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        self._is_ready = False

    @property
    def bucket(self) -> str:
        return self._bucket

    async def ensure_ready(self) -> None:
        """ensure_bucket один раз за жизнь процесса (MinIO мог не успеть подняться к старту backend)."""
        if not self._is_ready:
            await self.ensure_bucket()
            self._is_ready = True

    async def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self._bucket)
            return
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket", "NotFound"):
                raise
        await asyncio.to_thread(self._client.create_bucket, Bucket=self._bucket)
        logger.info("Создан bucket %s для вложений", self._bucket)

    async def put(self, key: str, fileobj: BinaryIO) -> None:
        """Загрузить файл (большие — частями, multipart upload)."""
        await asyncio.to_thread(
            self._client.upload_fileobj,
            fileobj,
            self._bucket,
            key,
            ExtraArgs={"ContentType": STORED_CONTENT_TYPE},
        )

    async def stream(self, key: str) -> AsyncIterator[bytes]:
        """Содержимое объекта кусками по CHUNK_SIZE. Объект открывается до первого куска."""
        response = await asyncio.to_thread(self._client.get_object, Bucket=self._bucket, Key=key)
        body = response["Body"]

        async def chunks() -> AsyncIterator[bytes]:
            try:
                while chunk := await asyncio.to_thread(body.read, CHUNK_SIZE):
                    yield chunk
            finally:
                body.close()

        return chunks()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def delete_many(self, keys: Iterable[str]) -> list[str]:
        """Удалить объекты пачками. Вернуть ключи, которые удалить не удалось."""
        keys = list(keys)
        failed: list[str] = []
        for start in range(0, len(keys), DELETE_BATCH):
            batch = keys[start : start + DELETE_BATCH]
            response = await asyncio.to_thread(
                self._client.delete_objects,
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
            )
            failed.extend(err["Key"] for err in response.get("Errors", []))
        return failed

    # --- Синхронные методы для резервной копии (app/storage_backup.py) ---

    def iter_keys(self) -> Iterable[tuple[str, int]]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket):
            for obj in page.get("Contents", []):
                yield obj["Key"], obj["Size"]

    def open_sync(self, key: str) -> BinaryIO:
        return self._client.get_object(Bucket=self._bucket, Key=key)["Body"]

    def put_bytes_sync(self, key: str, data: bytes) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=STORED_CONTENT_TYPE)


def is_configured() -> bool:
    return bool(settings.s3_access_key and settings.s3_secret_key)


def build_storage() -> ObjectStorage:
    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        # path-style: MinIO и большинство S3-совместимых серверов без DNS-имён для bucket
        config=Config(
            s3={"addressing_style": "path"},
            connect_timeout=3,
            read_timeout=30,
            retries={"max_attempts": 2},
        ),
    )
    return ObjectStorage(client, settings.s3_bucket)


_storage: Optional[ObjectStorage] = None


def get_storage() -> ObjectStorage:
    """Хранилище из настроек. StorageUnavailable — если ключи не заданы."""
    global _storage
    if not is_configured():
        raise StorageUnavailable("Хранилище вложений не настроено (S3_ACCESS_KEY / MINIO_ROOT_USER)")
    if _storage is None:
        _storage = build_storage()
    return _storage


def reset_storage() -> None:
    """Пересоздать клиент при следующем обращении (тесты)."""
    global _storage
    _storage = None


async def prepare_attachments_storage() -> None:
    """При старте: создать bucket. Хранилище недоступно — не падаем, повторим при первой загрузке."""
    if not is_configured():
        logger.warning("Вложения выключены: не заданы ключи S3 (MINIO_ROOT_USER / S3_ACCESS_KEY)")
        return
    try:
        await get_storage().ensure_ready()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Хранилище вложений недоступно при старте: %s", exc)
