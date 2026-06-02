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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Singleton — импортировать отсюда
settings = Settings()
