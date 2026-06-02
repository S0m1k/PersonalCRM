"""
Конфигурация приложения — читается из переменных окружения / .env файла.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "personalcrm"

    # Безопасность (заглушка — будет использоваться в Sprint 1 для JWT)
    secret_key: str = "change-me-in-production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# Singleton — импортировать отсюда
settings = Settings()
