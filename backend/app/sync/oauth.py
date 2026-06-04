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

_MS_SCOPES = "Contacts.Read User.Read offline_access"

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


async def ms_refresh_token(refresh_token: str) -> dict:
    """
    Обновить истекший access_token через refresh_token.

    Возвращает новый dict с токенами (аналогично ms_exchange_code).
    """
    token_url = f"https://login.microsoftonline.com/{settings.ms_tenant}/oauth2/v2.0/token"
    payload = {
        "client_id": settings.ms_client_id,
        "client_secret": settings.ms_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": _MS_SCOPES,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(token_url, data=payload)
        resp.raise_for_status()
        data = resp.json()

    logger.info("ms_refresh_token: токены обновлены, expires_in=%s", data.get("expires_in"))
    return data


# ===========================================================================
# Google OAuth 2.0 (Sprint 3)
# ===========================================================================

_GOOGLE_SCOPES = "https://www.googleapis.com/auth/contacts"
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
