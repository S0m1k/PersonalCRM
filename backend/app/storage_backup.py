"""
Резервная копия файлов-вложений: все объекты bucket'а в tar.gz-поток и обратно.

Работает с любым S3 (не только MinIO). Запускается внутри контейнера backend,
поток идёт через stdout/stdin — так его вызывает scripts/backup.py:

    docker compose exec -T backend python -m app.storage_backup dump > files.tar.gz
    docker compose exec -T backend python -m app.storage_backup restore < files.tar.gz

restore дописывает и перезаписывает объекты из архива; лишние объекты в bucket не удаляются
(метаданные в MongoDB восстанавливаются отдельно, из дампа базы).
"""

from __future__ import annotations

import asyncio
import sys
import tarfile
from typing import BinaryIO

from .storage import ObjectStorage, get_storage


def dump(storage: ObjectStorage, out: BinaryIO) -> int:
    """Записать все объекты в tar.gz-поток. Вернуть их число."""
    count = 0
    with tarfile.open(fileobj=out, mode="w|gz") as tar:
        for key, size in storage.iter_keys():
            info = tarfile.TarInfo(name=key)
            info.size = size
            body = storage.open_sync(key)
            try:
                tar.addfile(info, body)
            finally:
                body.close()
            count += 1
    return count


def restore(storage: ObjectStorage, src: BinaryIO) -> int:
    """Загрузить объекты из tar.gz-потока. Вернуть их число."""
    count = 0
    with tarfile.open(fileobj=src, mode="r|gz") as tar:
        for member in tar:
            if not member.isfile() or member.name.startswith("/") or ".." in member.name.split("/"):
                continue
            fileobj = tar.extractfile(member)
            if fileobj is None:
                continue
            # Поток tar не перематывается — файл целиком в память (вложения не больше ATTACHMENT_MAX_MB)
            storage.put_bytes_sync(member.name, fileobj.read())
            count += 1
    return count


def main(argv: list[str]) -> int:
    if argv not in (["dump"], ["restore"]):
        print("Использование: python -m app.storage_backup dump|restore", file=sys.stderr)
        return 2
    storage = get_storage()
    asyncio.run(storage.ensure_ready())
    if argv == ["dump"]:
        count = dump(storage, sys.stdout.buffer)
    else:
        count = restore(storage, sys.stdin.buffer)
    print(f"Файлов: {count}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
