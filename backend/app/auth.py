"""
Аутентификация: пользователи с паролями (bcrypt) и JWT.

- Пользователи — в коллекции users системной базы (repositories/users.py).
- Токены подписываются settings.secret_key (HS256), sub = id пользователя,
  v = версия токенов пользователя (растёт при смене пароля — старые токены перестают работать).
- get_current_user поднимает 401 на невалидный токен или удалённого пользователя.
- get_user_db отдаёт базу с данными текущего пользователя — её используют роутеры.
- Прежний единственный пользователь (ADMIN_USERNAME / ADMIN_PASSWORD) при старте
  становится обычным пользователем, а его данные остаются в системной базе.
- bcrypt медленный (~0.25 с) — в async-коде он идёт через asyncio.to_thread.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from .config import settings
from .db import get_db
from .models.user import PASSWORD_MIN, User
from .repositories import users as users_repo

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


async def hash_password_async(plain: str) -> str:
    return await asyncio.to_thread(hash_password, plain)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed)


def create_access_token(
    subject: str, expires_delta: Optional[timedelta] = None, token_version: int = 0
) -> str:
    """Создать подписанный JWT-токен."""
    _require_deps()
    delta = expires_delta or timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + delta
    payload = {"sub": subject, "exp": expire, "v": token_version}
    return _jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)  # type: ignore[union-attr]


def decode_token_claims(token: str) -> Optional[dict]:
    """Проверенные claims токена или None (истёк, неверная подпись, нет sub …)."""
    _require_deps()
    try:
        payload = _jwt.decode(  # type: ignore[union-attr]
            token, settings.secret_key, algorithms=[ALGORITHM]
        )
    except JWTError:
        return None
    return payload if isinstance(payload.get("sub"), str) else None


def decode_token(token: str) -> Optional[str]:
    """Декодировать JWT и вернуть subject (id пользователя) или None."""
    claims = decode_token_claims(token)
    return claims["sub"] if claims else None


def token_for(user: User) -> str:
    return create_access_token(subject=user.id, token_version=user.token_version)


# ---------------------------------------------------------------------------
# Пользователи
# ---------------------------------------------------------------------------

# Хеш-заглушка: при входе с несуществующим email всё равно тратим время на bcrypt,
# чтобы по времени ответа нельзя было узнать, зарегистрирован ли адрес
_DUMMY_HASH: Optional[str] = None


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("timing-equalizer")
    return _DUMMY_HASH


def carddav_digest(password: str) -> str:
    """
    Отпечаток пароля CardDAV. Телефон шлёт пароль на каждый запрос (десятки за синхронизацию),
    bcrypt тут слишком медленный; пароли генерирует сервер (высокая энтропия),
    поэтому достаточно HMAC-SHA256 с секретом приложения.
    """
    return hmac.new(settings.secret_key.encode(), password.encode(), hashlib.sha256).hexdigest()


def webhook_client_state(user_id: str, connection_id: str) -> str:
    """
    clientState подписки Microsoft: «<пользователь>:<подключение>:<подпись>».
    Вебхук приходит без JWT — подпись не даёт по угаданным id запускать чужие синхронизации.
    Microsoft ограничивает clientState 128 символами, здесь их ~82.
    """
    payload = f"{user_id}:{connection_id}"
    signature = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{payload}:{signature}"


def parse_webhook_client_state(value: object) -> Optional[tuple[str, str]]:
    """(id пользователя, id подключения) или None, если подпись не сходится."""
    if not isinstance(value, str) or value.count(":") != 2:
        return None
    user_id, connection_id, _ = value.split(":")
    if not user_id or not connection_id:
        return None
    expected = webhook_client_state(user_id, connection_id)
    return (user_id, connection_id) if hmac.compare_digest(value, expected) else None


# Базы, где перенос уже проверен: дальше — только поиск в множестве, без запросов к MongoDB
_legacy_checked: set[tuple[int, str]] = set()


def _legacy_password_hash() -> Optional[str]:
    """Хеш пароля первого пользователя или None, если он не задан надёжно."""
    if settings.admin_password_hash:
        return settings.admin_password_hash
    password = settings.admin_password or ""
    if len(password) < PASSWORD_MIN:
        return None
    return hash_password(password)


async def ensure_legacy_admin(db: AsyncIOMotorDatabase) -> None:
    """
    Перенос из однопользовательской версии: если в настройках есть ADMIN_USERNAME
    с надёжным паролем, а такого пользователя ещё нет — создать его с базой = системной
    (там лежат старые данные). Пароль короче 8 символов (в т.ч. «admin» из примера .env)
    не переносится: на публичном адресе это открытая дверь.
    """
    db_key = (id(db.client), db.name)
    if db_key in _legacy_checked or not settings.admin_username:
        return
    await users_repo.ensure_indexes(db)
    if await users_repo.get_auth_doc(db, settings.admin_username) is None:
        password_hash = await asyncio.to_thread(_legacy_password_hash)
        if password_hash is None:
            logger.warning(
                "Первый пользователь %s не создан: задайте ADMIN_PASSWORD_HASH или ADMIN_PASSWORD "
                "не короче %d символов",
                settings.admin_username,
                PASSWORD_MIN,
            )
        else:
            secret = carddav_digest(settings.carddav_password) if settings.carddav_password else None
            try:
                await users_repo.create_user(
                    db,
                    email=settings.admin_username,
                    password_hash=password_hash,
                    name=settings.admin_username,
                    db_name=db.name,
                    is_admin=True,
                    carddav_secret=secret,
                )
                logger.info("Создан пользователь %s из настроек однопользовательской версии", settings.admin_username)
            except users_repo.EmailTakenError:
                pass  # параллельный запрос успел первым
    _legacy_checked.add(db_key)


def reset_legacy_check() -> None:
    """Снова проверить перенос первого пользователя (тесты)."""
    _legacy_checked.clear()


async def authenticate_user(db: AsyncIOMotorDatabase, login: str, password: str) -> Optional[User]:
    """Проверить логин (email) и пароль. None — если не подходят."""
    await ensure_legacy_admin(db)
    doc = await users_repo.get_auth_doc(db, login)
    if doc is None:
        await verify_password_async(password, await asyncio.to_thread(_dummy_hash))
        return None
    if not await verify_password_async(password, doc.get("password_hash", "")):
        return None
    return User.from_mongo(doc)


def tenant_db(system_db: AsyncIOMotorDatabase, db_name: str) -> AsyncIOMotorDatabase:
    """База пользователя на том же подключении, что и системная."""
    if db_name == system_db.name:
        return system_db
    return system_db.client[db_name]


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> User:
    """
    Извлекает и валидирует Bearer-токен. 401 — если токен отсутствует, просрочен,
    подпись неверна или пользователя уже нет.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Недействительный или просроченный токен",
        headers={"WWW-Authenticate": "Bearer"},
    )
    claims = decode_token_claims(token)
    if claims is None:
        raise credentials_exception
    user = await users_repo.get_user(db, claims["sub"])
    # Токен, выданный до смены пароля, больше не действует
    if user is None or claims.get("v", 0) != user.token_version:
        raise credentials_exception
    return user


async def get_user_db(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncIOMotorDatabase, Depends(get_db)],
) -> AsyncIOMotorDatabase:
    """База с данными текущего пользователя."""
    return tenant_db(db, user.db_name)
