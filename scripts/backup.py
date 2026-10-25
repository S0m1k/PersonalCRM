"""
Резервная копия и восстановление баз MongoDB и файлов-вложений из docker-compose.

В копию попадают системная база personalcrm (пользователи и данные первого
пользователя), базы всех пользователей personalcrm_u_<id> и рядом — архив
файлов-вложений из S3 / MinIO: personalcrm-files-<время>.tar.gz.

    python scripts/backup.py                         # копия в ./backups, хранить 14 последних
    python scripts/backup.py --dir D:/OneDrive/crm   # копия в другую папку (лучше — вне этого диска)
    python scripts/backup.py --keep 30
    python scripts/backup.py --restore backups/personalcrm-20261021-0300.archive.gz

Восстановление ПОЛНОСТЬЮ заменяет текущие базы CRM содержимым копии; файлы из архива
рядом (если он есть) дописываются в хранилище.
Нужен запущенный `docker compose up` (сервисы mongo и backend). Только стандартная библиотека Python.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_NAME = "personalcrm"
PREFIX = f"{DB_NAME}-"
SUFFIX = ".archive.gz"
FILES_PREFIX = f"{DB_NAME}-files-"
FILES_SUFFIX = ".tar.gz"
# Базы пользователей: personalcrm_u_<id> (см. backend/app/repositories/users.py)
NS_INCLUDE = [f"--nsInclude={DB_NAME}.*", f"--nsInclude={DB_NAME}_u_*.*"]
DROP_CRM_DATABASES = (
    "db.adminCommand({listDatabases: 1}).databases"
    f".filter(d => d.name === '{DB_NAME}' || d.name.startsWith('{DB_NAME}_u_'))"
    ".forEach(d => db.getSiblingDB(d.name).dropDatabase())"
)


def _compose_exec(*args: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", "mongo", *args]


def _backend_exec(*args: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", "backend", *args]


def files_archive_for(db_archive: Path) -> Path:
    """Архив файлов-вложений, снятый вместе с этим дампом базы (то же время в имени)."""
    stamp = db_archive.name.removeprefix(PREFIX).removesuffix(SUFFIX)
    return db_archive.with_name(f"{FILES_PREFIX}{stamp}{FILES_SUFFIX}")


def backup_files(path: Path) -> None:
    """Все объекты хранилища вложений — в tar.gz. Снимает backend, поэтому годится любой S3, не только MinIO."""
    with path.open("wb") as out:
        result = subprocess.run(
            _backend_exec("python", "-m", "app.storage_backup", "dump"),
            cwd=ROOT, stdout=out, stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(
            "Копия базы сохранена, но файлы-вложения скопировать не удалось:\n"
            + result.stderr.decode(errors="replace")
        )


def restore_files(path: Path) -> None:
    """Дописать файлы из архива в хранилище (объекты с теми же ключами перезаписываются)."""
    with path.open("rb") as src:
        result = subprocess.run(
            _backend_exec("python", "-m", "app.storage_backup", "restore"),
            cwd=ROOT, stdin=src, stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Не удалось восстановить файлы-вложения:\n{result.stderr.decode(errors='replace')}")


def make_backup(target_dir: Path, keep: int) -> Path:
    """Снять дамп всех баз CRM и файлов-вложений, удалить старые копии сверх `keep`."""
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{PREFIX}{datetime.now():%Y%m%d-%H%M%S}{SUFFIX}"
    with path.open("wb") as out:
        result = subprocess.run(
            # Без --db mongodump снимает все базы сервера (на нём только CRM),
            # лишнее отсекается при восстановлении через --nsInclude
            _compose_exec("mongodump", "--archive", "--gzip"),
            cwd=ROOT, stdout=out, stderr=subprocess.PIPE,
        )
    if result.returncode != 0 or path.stat().st_size == 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"mongodump завершился с ошибкой:\n{result.stderr.decode(errors='replace')}")
    backup_files(files_archive_for(path))
    prune(target_dir, keep)
    return path


def prune(target_dir: Path, keep: int) -> list[Path]:
    """Удалить самые старые копии, оставив `keep` последних. Вернуть удалённые."""
    backups = sorted(target_dir.glob(f"{PREFIX}*{SUFFIX}"))
    stale = backups[:-keep] if keep > 0 else []
    for old in stale:
        old.unlink()
        files_archive_for(old).unlink(missing_ok=True)
    return stale


def restore(archive: Path) -> None:
    """Заменить базы CRM содержимым архива целиком (базы и коллекции, которых нет в копии, удаляются)."""
    if not archive.is_file():
        raise FileNotFoundError(archive)
    # mongorestore --drop пересоздаёт только коллекции из архива — более новые остались бы
    dropped = subprocess.run(
        _compose_exec("mongosh", DB_NAME, "--quiet", "--eval", DROP_CRM_DATABASES),
        cwd=ROOT, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL,
    )
    if dropped.returncode != 0:
        raise RuntimeError(f"Не удалось очистить базу перед восстановлением:\n{dropped.stderr.decode(errors='replace')}")
    with archive.open("rb") as src:
        result = subprocess.run(
            _compose_exec("mongorestore", "--archive", "--gzip", "--drop", *NS_INCLUDE),
            cwd=ROOT, stdin=src, stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise RuntimeError(f"mongorestore завершился с ошибкой:\n{result.stderr.decode(errors='replace')}")
    files = files_archive_for(archive)
    if files.is_file():
        restore_files(files)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Резервная копия базы PersonalCRM")
    parser.add_argument("--dir", type=Path, default=ROOT / "backups", help="папка для копий")
    parser.add_argument("--keep", type=int, default=14, help="сколько последних копий хранить")
    parser.add_argument("--restore", type=Path, help="восстановить базу из этого архива")
    args = parser.parse_args(argv)

    try:
        if args.restore:
            restore(args.restore)
            print(f"База восстановлена из {args.restore}")
        else:
            path = make_backup(args.dir, args.keep)
            files = files_archive_for(path)
            print(f"Копия сохранена: {path} ({path.stat().st_size // 1024} КБ)")
            print(f"Файлы-вложения: {files} ({files.stat().st_size // 1024} КБ)")
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
