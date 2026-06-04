"""
Конфигурация приложения — читается из переменных окружения / .env файла.
"""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "personalcrm"

    # Безопасность — JWT
    secret_key: str = "change-me-in-production"
    jwt_expire_minutes: int = 60 * 24  # 24 часа

    # Single-user аутентификация
    admin_username: str = "admin"
    # Для локальной разработки: задайте ADMIN_PASSWORD в .env
    # Для продакшна: задайте ADMIN_PASSWORD_HASH (bcrypt) и не храните plaintext
    admin_password: str = "admin"
    admin_password_hash: Optional[str] = None  # bcrypt-хеш; если задан — используется вместо admin_password

    # Шифрование токенов OAuth (Sprint 2)
    # Base64-encoded 32-байтный Fernet-ключ. Если не задан — выводится из secret_key (только для dev!).
    # Генерация: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: Optional[str] = None

    # Microsoft Graph OAuth (Sprint 2)
    # Регистрация приложения в Azure AD: https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps
    ms_client_id: Optional[str] = None
    ms_client_secret: Optional[str] = None
    ms_tenant: str = "common"          # "common" — для мультитенантных приложений
    ms_redirect_uri: str = "http://localhost:8000/api/sync/callback/microsoft"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Singleton — импортировать отсюда
settings = Settings()
