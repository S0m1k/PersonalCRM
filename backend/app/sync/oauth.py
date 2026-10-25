"""
Microsoft OAuth 2.0 helpers.

Функции:
  - ms_authorize_url   — строит URL для редиректа пользователя на Microsoft login
  - ms_exchange_code   — меняет authorization code на access_token + refresh_token
  - ms_refresh_token   — обновляет истекший access_token через refresh_token

Конфигурация (config.py / .env):
  MS_CLIENT_ID       — Application (client) ID из Azure AD app registration
  MS_CLIENT_SECRET   — Client secret
  MS_TENANT          — "common" (default) или конкретный tenant ID
  MS_REDIRECT_URI    — должен совпадать с redirect URI в Azure AD

Если MS_CLIENT_ID или MS_CLIENT_SECRET не заданы — функции connect-endpoint
вернут 501, не роняя приложение при старте.
"""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# ReadWrite — нужен для двустороннего sync (push правок из CRM в Outlook).
# Calendars.ReadWrite добавлен в Sprint 7: подключения, выданные раньше, его не имеют —
# их нужно переподключить (calendar_scope_granted покажет, есть ли доступ).
_MS_SCOPES = "Contacts.ReadWrite Calendars.ReadWrite User.Read offline_access"
# Права подключений до Sprint 7: с ними обновляем токены, если выданные права неизвестны
_MS_LEGACY_SCOPES = "Contacts.ReadWrite User.Read offline_access"

# ---------------------------------------------------------------------------
# Проверка наличия конфигурации
# ---------------------------------------------------------------------------


def ms_configured() -> bool:
    """True если Azure AD credentials заданы в настройках."""
    return bool(settings.ms_client_id and settings.ms_client_secret)


# ---------------------------------------------------------------------------
# Authorization URL
# ---------------------------------------------------------------------------


def ms_authorize_url(state: str = "") -> str:
    """
    Построить URL для OAuth authorize redirect.

    state — произвольная строка для защиты от CSRF (рекомендуется uuid4).
    """
    if not ms_configured():
        raise RuntimeError(
            "Microsoft OAuth не настроен. Задайте MS_CLIENT_ID и MS_CLIENT_SECRET в .env. "
            "Подробнее: https://docs.microsoft.com/azure/active-directory/develop/quickstart-register-app"
        )

    params = {
        "client_id": settings.ms_client_id,
        "response_type": "code",
        "redirect_uri": settings.ms_redirect_uri,
        "scope": _MS_SCOPES,
        "response_mode": "query",
    }
    if state:
        params["state"] = state

    base = f"https://login.microsoftonline.com/{settings.ms_tenant}/oauth2/v2.0/authorize"
    return f"{base}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Token exchange
# ---------------------------------------------------------------------------


async def ms_exchange_code(code: str) -> dict:
    """
    Обменять authorization code на токены.

    Возвращает dict с ключами:
      access_token, refresh_token (если запрошен offline_access),
      expires_in (секунды), token_type, scope.

    Поднимает httpx.HTTPStatusError при ошибке от Microsoft.
    """
    token_url = f"https://login.microsoftonline.com/{settings.ms_tenant}/oauth2/v2.0/token"
    payload = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "code": code,
        "redirect_uri": settings.ms_redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=payload)
        resp.raise_for_status()
        data = resp.json()

    logger.info("ms_exchange_code: токены получены, expires_in=%s", data.get("expires_in"))
    return data


async def ms_refresh_token(refresh_token: str, scopes: Optional[str] = None) -> dict:
    """
    Обновить истекший access_token через refresh_token.

    scopes — права, выданные подключению (из ответа на обмен кода). Просить при обновлении
    больше, чем выдано, нельзя — Microsoft ответит ошибкой, поэтому для старых подключений
    (права неизвестны) просим права до Sprint 7.

    Возвращает новый dict с токенами (аналогично ms_exchange_code).
    """
    token_url = f"https://login.microsoftonline.com/{settings.ms_tenant}/oauth2/v2.0/token"
    payload = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": _ms_refresh_scopes(scopes),
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=payload)
        resp.raise_for_status()
        data = resp.json()

    logger.info("ms_refresh_token: токены обновлены, expires_in=%s", data.get("expires_in"))
    return data


def _ms_refresh_scopes(granted: Optional[str]) -> str:
    """Права для refresh: выданные (только из запрошенных нами) или права до Sprint 7."""
    if not granted:
        return _MS_LEGACY_SCOPES
    wanted = {s.lower(): s for s in _MS_SCOPES.split()}
    names = {g.rsplit("/", 1)[-1].lower() for g in granted.split()}
    picked = [wanted[n] for n in wanted if n in names]
    if "offline_access" not in [p.lower() for p in picked]:
        picked.append("offline_access")
    return " ".join(picked)


# ===========================================================================
# Google OAuth 2.0 (Sprint 3)
# ===========================================================================

# calendar.events — чтение и запись событий (Sprint 7); подключения до Sprint 7 его не имеют
_GOOGLE_SCOPES = "https://www.googleapis.com/auth/contacts https://www.googleapis.com/auth/calendar.events"
_GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def google_configured() -> bool:
    """True если Google OAuth credentials заданы."""
    return bool(settings.google_client_id and settings.google_client_secret)


def google_authorize_url(state: str = "") -> str:
    """Построить URL для Google OAuth authorize redirect."""
    if not google_configured():
        raise RuntimeError(
            "Google OAuth не настроен. Задайте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET в .env. "
            "Регистрация: https://console.cloud.google.com/apis/credentials"
        )

    params = {
        "client_id": settings.google_client_id,
        "response_type": "code",
        "redirect_uri": settings.google_redirect_uri,
        "scope": _GOOGLE_SCOPES,
        "access_type": "offline",   # чтобы получить refresh_token
        "prompt": "consent",        # форсим refresh_token при повторном connect
        "include_granted_scopes": "true",  # переподключение добавляет права к уже выданным
    }
    if state:
        params["state"] = state

    return f"{_GOOGLE_AUTH_URL}?{urlencode(params)}"


async def google_exchange_code(code: str) -> dict:
    """Обменять authorization code на токены Google."""
    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "code": code,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()

    logger.info("google_exchange_code: токены получены, expires_in=%s", data.get("expires_in"))
    return data


async def google_refresh_token(refresh_token: str) -> dict:
    """Обновить истекший access_token Google через refresh_token."""
    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(_GOOGLE_TOKEN_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()

    # Google при refresh не возвращает новый refresh_token — сохраняем старый
    logger.info("google_refresh_token: токены обновлены, expires_in=%s", data.get("expires_in"))
    return data


# ===========================================================================
# Есть ли у подключения доступ к календарю
# ===========================================================================


def calendar_scope_granted(provider: str, scopes: Optional[str]) -> bool:
    """
    По строке выданных прав (поле scope ответа OAuth) — можно ли читать и писать календарь.
    None — подключение создано до Sprint 7 (права не сохранялись) → доступа нет.
    """
    if not scopes:
        return False
    granted = {s.lower() for s in scopes.split()}
    if provider == "microsoft":
        return any(s.rsplit("/", 1)[-1] == "calendars.readwrite" for s in granted)
    if provider == "google":
        return bool(
            granted & {"https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar"}
        )
    return False
