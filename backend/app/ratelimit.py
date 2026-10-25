"""
Рейт-лимиты на все запросы к backend.

Правила подбираются по методу и пути (первое совпавшее). Ключ — пользователь
(sub из JWT) или IP клиента для запросов без токена (вход, регистрация, CardDAV,
вебхуки); IPv6 — по сети /64 (у одного клиента их миллиарды). Вход дополнительно
ограничен на аккаунт (check_login_attempt). Счётчики — в Redis (REDIS_URL),
без него — в памяти процесса. Окно скользящее и точное (moving window).

Если Redis недоступен, запросы пропускаются (fail-open) с предупреждением в логе:
лимиты защищают от перегрузки и перебора паролей, но не должны класть CRM целиком.
"""

from __future__ import annotations

import ipaddress
import logging
import math
import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from limits import RateLimitItem, parse_many
from limits.aio.storage import MemoryStorage, RedisStorage, Storage
from limits.aio.strategies import MovingWindowRateLimiter
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .auth import decode_token
from .config import settings

logger = logging.getLogger(__name__)

KeyKind = Literal["ip", "user"]
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
# Не чаще одного предупреждения о недоступном Redis за этот интервал
STORAGE_WARN_INTERVAL_S = 60
REDIS_TIMEOUT_S = 0.3
# После сбоя хранилища столько секунд не обращаемся к нему (запросы идут без лимитов)
STORAGE_RETRY_AFTER_S = 30


@dataclass(frozen=True)
class Rule:
    name: str
    limits: tuple[RateLimitItem, ...]
    key: KeyKind
    matches: Callable[[str, str], bool]


def _rule(name: str, spec: str, key: KeyKind, matches: Callable[[str, str], bool]) -> Rule:
    return Rule(name=name, limits=tuple(parse_many(spec)), key=key, matches=matches)


def _is_dav(path: str) -> bool:
    return path == "/dav" or path.startswith("/dav/") or path == "/.well-known/carddav"


def _is_attachment_upload(path: str) -> bool:
    return path.startswith("/api/contacts/") and path.rstrip("/").endswith("/attachments")


RULES: tuple[Rule, ...] = (
    # Без токена — по IP: перебор паролей и массовая регистрация
    _rule("register", "5/hour;20/day", "ip", lambda m, p: m == "POST" and p == "/api/auth/register"),
    _rule("login", "10/minute;60/hour", "ip", lambda m, p: m == "POST" and p.startswith("/api/auth/login")),
    _rule("dav", "300/minute", "ip", lambda m, p: _is_dav(p)),
    _rule("webhook", "120/minute", "ip", lambda m, p: p.startswith("/api/webhooks/")),
    # Проверка текущего пароля и выпуск паролей для телефона
    _rule("credentials", "10/minute;30/hour", "user",
          lambda m, p: m != "GET" and p in ("/api/auth/password", "/api/auth/carddav-password")),
    # Тяжёлые операции: разбор файлов и походы во внешние API
    _rule("import", "20/hour", "user", lambda m, p: m == "POST" and p.startswith("/api/import/")),
    _rule("sync", "30/minute;300/hour", "user", lambda m, p: m == "POST" and p.startswith("/api/sync/")),
    # Загрузка вложений: до 25 МБ каждое — трафик и место на диске
    _rule("upload", "30/hour;200/day", "user", lambda m, p: m == "POST" and _is_attachment_upload(p)),
    # Изменения событий календаря ходят в Outlook / Google
    _rule("calendar", "30/minute;300/hour", "user",
          lambda m, p: m not in READ_METHODS and p.startswith("/api/calendar/")),
    # ИИ: каждый запрос — минуты работы видеокарты (применение предпросмотра — обычная запись)
    _rule("ai", "6/minute;60/hour;200/day", "user",
          lambda m, p: m == "POST" and p in ("/api/assistant/capture", "/api/assistant/ask")),
    # Всё остальное API
    _rule("write", "60/minute;1000/hour", "user", lambda m, p: m not in READ_METHODS and p.startswith("/api/")),
    _rule("read", "300/minute", "user", lambda m, p: p.startswith("/api/") and p != "/api/health"),
)


# Попытки входа в один аккаунт — с любых адресов (перебор пароля с ботнета)
LOGIN_ACCOUNT_RULE = _rule("login-account", "20/hour", "user", lambda m, p: False)


def find_rule(method: str, path: str) -> Optional[Rule]:
    return next((r for r in RULES if r.matches(method, path)), None)


def _ip_bucket(raw: str) -> str:
    """IPv4 — как есть, IPv6 — сеть /64."""
    try:
        ip = ipaddress.ip_address(raw)
    except ValueError:
        return raw
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def client_ip(request: Request) -> str:
    """
    IP клиента. За прокси (TRUST_PROXY_HEADERS=true) — из X-Real-IP: deploy/Caddyfile
    перезаписывает его адресом клиента (header_up X-Real-IP {client_ip}), поэтому подделать
    его нельзя. Сам backend при этом наружу не открыт — только через Caddy.
    """
    if settings.trust_proxy_headers:
        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return _ip_bucket(real_ip)
    return _ip_bucket(request.client.host) if request.client else "unknown"


def _user_key(request: Request) -> Optional[str]:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return decode_token(token)


def request_key(rule: Rule, request: Request) -> str:
    if rule.key == "user":
        user_id = _user_key(request)
        if user_id:
            return f"user:{user_id}"
    return f"ip:{client_ip(request)}"


class RateLimiter:
    def __init__(self, storage: Storage) -> None:
        self._limiter = MovingWindowRateLimiter(storage)
        self._last_warning = 0.0
        self._skip_until = 0.0

    async def check(self, rule: Rule, key: str) -> Optional[int]:
        """None — можно; иначе — через сколько секунд повторить."""
        if time.monotonic() < self._skip_until:
            return None
        try:
            for item in rule.limits:
                if not await self._limiter.hit(item, rule.name, key):
                    stats = await self._limiter.get_window_stats(item, rule.name, key)
                    return max(1, math.ceil(stats.reset_time - time.time()))
        except Exception as exc:  # noqa: BLE001 — хранилище недоступно: пропускаем
            now = time.monotonic()
            self._skip_until = now + STORAGE_RETRY_AFTER_S
            if now - self._last_warning > STORAGE_WARN_INTERVAL_S:
                self._last_warning = now
                logger.warning("Рейт-лимиты не работают, хранилище недоступно: %s", exc)
        return None


def build_limiter() -> RateLimiter:
    if settings.redis_url:
        uri = settings.redis_url
        if not uri.startswith("async+"):
            uri = f"async+{uri}"
        # Короткие таймауты: при упавшем Redis запрос не должен ждать секундами
        return RateLimiter(
            RedisStorage(
                uri,
                implementation="redispy",
                socket_connect_timeout=REDIS_TIMEOUT_S,
                socket_timeout=REDIS_TIMEOUT_S,
            )
        )
    return RateLimiter(MemoryStorage())


_limiter: Optional[RateLimiter] = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = build_limiter()
    return _limiter


def reset_limiter() -> None:
    """Сбросить счётчики (тесты)."""
    global _limiter
    _limiter = None


async def check_login_attempt(login: str) -> Optional[int]:
    """Попытка входа в аккаунт login. None — можно, иначе — через сколько секунд."""
    if not settings.rate_limit_enabled:
        return None
    return await get_limiter().check(LOGIN_ACCOUNT_RULE, f"login:{login}")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.rate_limit_enabled:
            return await call_next(request)
        rule = find_rule(request.method, request.url.path)
        if rule is None:
            return await call_next(request)
        retry_after = await get_limiter().check(rule, request_key(rule, request))
        if retry_after is not None:
            logger.info("rate limit %s hit for %s", rule.name, request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Слишком много запросов. Попробуйте позже."},
                headers={"Retry-After": str(retry_after)},
            )
        return await call_next(request)
