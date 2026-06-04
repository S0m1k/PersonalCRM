"""
Симметричное шифрование токенов OAuth с помощью Fernet (библиотека cryptography).

Использование:
    from app.crypto import encrypt, decrypt

    ciphertext = encrypt(access_token)
    plaintext  = decrypt(ciphertext)

Ключ:
    Приоритет 1 — переменная TOKEN_ENCRYPTION_KEY (base64-encoded Fernet key).
    Приоритет 2 — выводится из SECRET_KEY через PBKDF2-HMAC-SHA256 (только для dev!).
    В продакшне ОБЯЗАТЕЛЬНО задайте TOKEN_ENCRYPTION_KEY в .env.

Генерация ключа:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Получение/деривация ключа
# ---------------------------------------------------------------------------

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    if settings.token_encryption_key:
        # Используем явно заданный ключ
        key = settings.token_encryption_key.encode()
    else:
        # DEV fallback: выводим Fernet-ключ из secret_key через PBKDF2
        # WARNING: этот путь не предназначен для продакшна — задайте TOKEN_ENCRYPTION_KEY
        logger.warning(
            "TOKEN_ENCRYPTION_KEY не задан — ключ шифрования выводится из SECRET_KEY. "
            "Задайте TOKEN_ENCRYPTION_KEY в .env для продакшна."
        )
        raw = hashlib.pbkdf2_hmac(
            "sha256",
            settings.secret_key.encode("utf-8"),
            b"personalcrm-token-encryption-salt",
            iterations=100_000,
            dklen=32,
        )
        key = base64.urlsafe_b64encode(raw)

    _fernet = Fernet(key)
    return _fernet


# ---------------------------------------------------------------------------
# Публичный API
# ---------------------------------------------------------------------------


def encrypt(plaintext: str) -> str:
    """
    Зашифровать строку (токен OAuth) и вернуть base64-строку шифртекста.

    Используется перед сохранением токена в MongoDB.
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """
    Расшифровать ранее зашифрованный токен.

    Поднимает ValueError при испорченных/невалидных данных.
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Не удалось расшифровать токен: данные повреждены или ключ изменился") from exc
