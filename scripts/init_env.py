"""
Создать backend/.env и backend/minio.env из шаблонов *.example со случайными секретами.

    python scripts/init_env.py           # создать файлы, которых ещё нет (существующие не трогаются)
    python scripts/init_env.py --force   # перезаписать (старые OAuth-токены в базе станут нечитаемыми,
                                         # а MinIO с уже созданными данными не примет новый пароль!)

Секреты в консоль не выводятся — пароль входа смотрите в backend/.env (ADMIN_PASSWORD).
Только стандартная библиотека Python.
"""

from __future__ import annotations

import base64
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# (шаблон, рабочий файл)
FILES = [
    (ROOT / "backend" / ".env.example", ROOT / "backend" / ".env"),
    (ROOT / "backend" / "minio.env.example", ROOT / "backend" / "minio.env"),
]
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_secrets() -> dict[str, str]:
    """Новые значения для ключей, которые нельзя оставлять по умолчанию."""
    return {
        "SECRET_KEY": secrets.token_hex(32),
        "ADMIN_PASSWORD": secrets.token_urlsafe(12),
        # Fernet-ключ = urlsafe base64 от 32 случайных байт
        "TOKEN_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        # Пароль для телефона (CardDAV): только буквы и цифры — его вводят руками
        "CARDDAV_PASSWORD": "".join(secrets.choice(ALPHABET) for _ in range(16)),
        # Пароль MinIO (хранилище вложений): его же backend использует как S3-ключ
        "MINIO_ROOT_PASSWORD": secrets.token_urlsafe(24),
    }


def render(template: str, values: dict[str, str]) -> str:
    """Подставить значения в строки вида `KEY=...` или `# KEY=...` (раскомментируя их)."""
    lines = []
    for line in template.splitlines():
        match = re.match(r"^#?\s*([A-Z_]+)=", line)
        if match and match.group(1) in values:
            line = f"{match.group(1)}={values[match.group(1)]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    force = "--force" in argv
    values = generate_secrets()
    created = 0
    for template, target in FILES:
        if target.exists() and not force:
            print(f"{target} уже существует — не меняю (перезапись: --force).")
            continue
        target.write_text(render(template.read_text(encoding="utf-8"), values), encoding="utf-8")
        print(f"Создан {target}.")
        created += 1
    if created and FILES[0][1].exists():
        print("Пароль входа (пользователь admin) — в строке ADMIN_PASSWORD файла backend/.env.")
    return 0 if created else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
