"""
Резервная копия и восстановление базы MongoDB из docker-compose.

    python scripts/backup.py                         # копия в ./backups, хранить 14 последних
    python scripts/backup.py --dir D:/OneDrive/crm   # копия в другую папку (лучше — вне этого диска)
    python scripts/backup.py --keep 30
    python scripts/backup.py --restore backups/personalcrm-20261021-0300.archive.gz

Восстановление ПОЛНОСТЬЮ заменяет текущую базу содержимым копии.
Нужен запущенный `docker compose up` (сервис mongo). Только стандартная библиотека Python.
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


def _compose_exec(*args: str) -> list[str]:
    return ["docker", "compose", "exec", "-T", "mongo", *args]


def make_backup(target_dir: Path, keep: int) -> Path:
    """Снять дамп базы в файл и удалить старые копии сверх `keep`."""
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{PREFIX}{datetime.now():%Y%m%d-%H%M%S}{SUFFIX}"
    with path.open("wb") as out:
        result = subprocess.run(
            _compose_exec("mongodump", "--archive", "--gzip", f"--db={DB_NAME}"),
            cwd=ROOT, stdout=out, stderr=subprocess.PIPE,
        )
    if result.returncode != 0 or path.stat().st_size == 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"mongodump завершился с ошибкой:\n{result.stderr.decode(errors='replace')}")
    prune(target_dir, keep)
    return path


def prune(target_dir: Path, keep: int) -> list[Path]:
    """Удалить самые старые копии, оставив `keep` последних. Вернуть удалённые."""
    backups = sorted(target_dir.glob(f"{PREFIX}*{SUFFIX}"))
    stale = backups[:-keep] if keep > 0 else []
    for old in stale:
        old.unlink()
    return stale


def restore(archive: Path) -> None:
    """Заменить базу содержимым архива."""
    if not archive.is_file():
        raise FileNotFoundError(archive)
    with archive.open("rb") as src:
        result = subprocess.run(
            _compose_exec("mongorestore", "--archive", "--gzip", "--drop", f"--nsInclude={DB_NAME}.*"),
            cwd=ROOT, stdin=src, stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise RuntimeError(f"mongorestore завершился с ошибкой:\n{result.stderr.decode(errors='replace')}")


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
            print(f"Копия сохранена: {path} ({path.stat().st_size // 1024} КБ)")
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
