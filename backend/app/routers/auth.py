"""
Роутер аутентификации: /api/auth/login и /api/auth/me.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from ..auth import authenticate_user, create_access_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """Тело запроса при логине через JSON (альтернатива form-данным)."""

    username: str
    password: str


class MeResponse(BaseModel):
    username: str


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Получить JWT-токен",
    description=(
        "Принимает учётные данные через form (application/x-www-form-urlencoded) "
        "или JSON. Возвращает Bearer-токен."
    ),
)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """
    Логин через стандартный OAuth2 form (username + password).
    Совместим с /docs (кнопка Authorize).
    """
    if not authenticate_user(form_data.username, form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=form_data.username)
    return TokenResponse(access_token=token)


@router.post(
    "/login/json",
    response_model=TokenResponse,
    summary="Получить JWT-токен (JSON)",
    description="Принимает JSON {username, password}. Для фронтенда.",
)
async def login_json(body: LoginRequest) -> TokenResponse:
    """Логин через JSON-тело — удобно вызывать из fetch/axios."""
    if not authenticate_user(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(subject=body.username)
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Текущий пользователь",
)
async def me(current_user: str = Depends(get_current_user)) -> MeResponse:
    """Возвращает username текущего авторизованного пользователя."""
    return MeResponse(username=current_user)
