"""
Аутентификация: single-user JWT.

- Credentials хранятся в настройках (ADMIN_USERNAME, ADMIN_PASSWORD_HASH).
- Токены подписываются settings.secret_key (HS256).
- Dependency get_current_user поднимает 401 на невалидный / отсутствующий токен.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ленивый импорт тяжёлых зависимостей (passlib, jose)
# Они не были в Sprint 0 venv — приложение должно запускаться,
# только при реальном вызове auth-роутов будет ImportError если не установлены.
# ---------------------------------------------------------------------------

try:
    import bcrypt as _bcrypt
    from jose import JWTError, jwt as _jwt

    _DEPS_OK = True
except ImportError:  # pragma: no cover
    _DEPS_OK = False
    _bcrypt = None  # type: ignore[assignment]
    _jwt = None  # type: ignore[assignment]
    JWTError = Exception  # type: ignore[assignment,misc]


# bcrypt принимает максимум 72 байта — длинные пароли обрезаем (стандартная практика)
def _to_bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:72]


ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _require_deps() -> None:
    if not _DEPS_OK:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Auth-зависимости не установлены. "
                "Выполните: pip install bcrypt python-jose[cryptography]"
            ),
        )


def verify_password(plain: str, hashed: str) -> bool:
    _require_deps()
    try:
        return _bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("utf-8"))  # type: ignore[union-attr]
    except ValueError:
        # Некорректный (нестандартный) хеш
        return False


def hash_password(plain: str) -> str:
    _require_deps()
    return _bcrypt.hashpw(_to_bcrypt_bytes(plain), _bcrypt.gensalt()).decode("utf-8")  # type: ignore[union-attr]


def _get_password_hash() -> str:
    """
    Возвращает bcrypt-хеш пароля администратора.

    Приоритет:
    1. ADMIN_PASSWORD_HASH (уже хешированный — для продакшна)
    2. hash(ADMIN_PASSWORD) — для локальной разработки
    """
    if settings.admin_password_hash:
        return settings.admin_password_hash
    # Хешируем дефолтный пароль при первом вызове (на старте приложения не вызывается)
    return hash_password(settings.admin_password)


def create_access_token(subject: str, expires_delta: Optional[timedelta] = None) -> str:
    """Создать подписанный JWT-токен."""
    _require_deps()
    delta = expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + delta
    payload = {"sub": subject, "exp": expire}
    return _jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)  # type: ignore[union-attr]


def decode_token(token: str) -> Optional[str]:
    """
    Декодировать JWT и вернуть subject.
    При любой ошибке (истёк, неверная подпись, …) — возвращает None.
    """
    _require_deps()
    try:
        payload = _jwt.decode(  # type: ignore[union-attr]
            token, settings.secret_key, algorithms=[ALGORITHM]
        )
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """
    Dependency — извлекает и валидирует Bearer-токен из заголовка Authorization.
    Поднимает 401 если токен отсутствует, просрочен или подпись неверна.
    Возвращает username (sub из payload).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительный или просроченный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )

    username = decode_token(token)
    if username is None:
        raise credentials_exception
    return username


# ---------------------------------------------------------------------------
# Вспомогательная функция для роутера /login
# ---------------------------------------------------------------------------


def authenticate_user(username: str, password: str) -> bool:
    """
    Проверить логин/пароль администратора.
    Возвращает True если совпадают.
    """
    if username != settings.admin_username:
        return False
    return verify_password(password, _get_password_hash())
