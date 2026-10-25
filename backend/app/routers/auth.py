"""
Роутер аутентификации: регистрация, вход, текущий пользователь, пароли.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel

from ..auth import (
    authenticate_user,
    carddav_digest,
    get_current_user,
    hash_password_async,
    token_for,
    verify_password_async,
)
from ..config import settings
from ..db import get_db
from ..models.user import PasswordChange, User, UserCreate, UserOut, normalize_login
from ..ratelimit import check_login_attempt
from ..repositories import users as users_repo

router = APIRouter(prefix="/api/auth", tags=["auth"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
UserDep = Annotated[User, Depends(get_current_user)]

# Пароль для телефона: только буквы и цифры без похожих (0/O, 1/l) — его вводят руками
CARDDAV_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"
CARDDAV_PASSWORD_LENGTH = 20


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """Тело запроса при логине через JSON (альтернатива form-данным)."""

    username: str
    password: str


class CarddavPasswordOut(BaseModel):
    """Новый пароль для телефона — показывается один раз."""

    username: str
    password: str


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Слишком много попыток входа в этот аккаунт. Попробуйте позже.",
        headers={"Retry-After": str(retry_after)},
    )


async def _login(db: AsyncIOMotorDatabase, login: str, password: str) -> TokenResponse:
    # Лимит на аккаунт — в дополнение к лимиту по IP: перебор пароля с многих адресов
    retry_after = await check_login_attempt(normalize_login(login))
    if retry_after is not None:
        raise _too_many(retry_after)
    user = await authenticate_user(db, login, password)
    if user is None:
        raise _unauthorized()
    return TokenResponse(access_token=token_for(user))


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Неверный логин или пароль",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация",
)
async def register(body: UserCreate, db: DbDep) -> TokenResponse:
    """Создать аккаунт (email + пароль) и сразу войти. Данные — в отдельной базе."""
    if not settings.registration_open:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Регистрация закрыта")
    if await users_repo.count_users(db) >= settings.max_users:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Регистрация временно закрыта: мест нет")
    try:
        user = await users_repo.create_user(
            db, email=body.email, password_hash=await hash_password_async(body.password), name=body.name
        )
    except users_repo.EmailTakenError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Этот email уже зарегистрирован"
        ) from None
    return TokenResponse(access_token=token_for(user))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Получить JWT-токен",
    description=(
        "Принимает учётные данные через form (application/x-www-form-urlencoded). "
        "Совместим с кнопкой Authorize в /docs. username — это email."
    ),
)
async def login(
    db: DbDep, form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> TokenResponse:
    return await _login(db, form_data.username, form_data.password)


@router.post(
    "/login/json",
    response_model=TokenResponse,
    summary="Получить JWT-токен (JSON)",
    description="Принимает JSON {username, password}; username — это email. Для фронтенда.",
)
async def login_json(body: LoginRequest, db: DbDep) -> TokenResponse:
    return await _login(db, body.username, body.password)


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
async def me(user: UserDep) -> UserOut:
    return UserOut.from_user(user)


@router.post(
    "/password",
    response_model=TokenResponse,
    summary="Сменить пароль",
    description="Все выданные ранее токены (другие устройства) перестают работать; в ответе — новый токен.",
)
async def change_password(body: PasswordChange, user: UserDep, db: DbDep) -> TokenResponse:
    doc = await users_repo.get_auth_doc(db, user.email)
    if doc is None or not await verify_password_async(body.current_password, doc.get("password_hash", "")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Текущий пароль неверен")
    version = await users_repo.set_password_hash(db, user.id, await hash_password_async(body.new_password))
    return TokenResponse(access_token=token_for(user.model_copy(update={"token_version": version})))


@router.post(
    "/carddav-password",
    response_model=CarddavPasswordOut,
    summary="Выпустить новый пароль для телефона (CardDAV)",
    description="Старый пароль перестаёт работать. Новый показывается только в этом ответе.",
)
async def issue_carddav_password(user: UserDep, db: DbDep) -> CarddavPasswordOut:
    password = "".join(secrets.choice(CARDDAV_ALPHABET) for _ in range(CARDDAV_PASSWORD_LENGTH))
    await users_repo.set_carddav_secret(db, user.id, carddav_digest(password))
    return CarddavPasswordOut(username=user.email, password=password)


@router.delete(
    "/carddav-password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    summary="Отключить доступ телефона (CardDAV)",
)
async def revoke_carddav_password(user: UserDep, db: DbDep) -> None:
    await users_repo.set_carddav_secret(db, user.id, None)
