"""
Конфигурация приложения — читается из переменных окружения / .env файла.
"""

from typing import Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET_KEY = "change-me-in-production"
SECRET_KEY_MIN_LENGTH = 32


class Settings(BaseSettings):
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    db_name: str = "personalcrm"

    # Безопасность — JWT. Обязателен: со значением по умолчанию backend не стартует (см. check_secrets)
    secret_key: str = INSECURE_SECRET_KEY
    jwt_expire_minutes: int = 60 * 24  # 24 часа

    # Первый пользователь из однопользовательской версии (см. auth.ensure_legacy_admin).
    # Создаётся, только если задан ADMIN_PASSWORD_HASH или ADMIN_PASSWORD не короче 8 символов.
    admin_username: str = "admin"
    # Для локальной разработки: задайте ADMIN_PASSWORD в .env
    # Для продакшна: задайте ADMIN_PASSWORD_HASH (bcrypt) и не храните plaintext
    admin_password: Optional[str] = None
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

    # Google People API OAuth (Sprint 3)
    # Регистрация: https://console.cloud.google.com/apis/credentials
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:8000/api/sync/callback/google"

    # Публичный базовый URL приложения (для webhook notificationUrl, Sprint 3).
    # На проде — https-домен; локально webhooks от Microsoft не приходят.
    public_base_url: str = "http://localhost:8000"

    # Адрес фронтенда: сюда OAuth callback возвращает браузер, и он же — разрешённый CORS origin.
    frontend_url: str = "http://localhost:3000"

    # Интервал фонового sync (мин). Без вебхуков (локальный запуск) — ставим поменьше, напр. 5.
    sync_interval_minutes: int = 30

    # CardDAV (контакты в iPhone / Android): логин ADMIN_USERNAME + этот пароль.
    # Отдельный пароль — его хранит телефон. Не задан — CardDAV выключен (404).
    carddav_password: Optional[str] = None

    # Пользователи. Открытая регистрация: любой может создать аккаунт (данные — в своей базе).
    registration_open: bool = True
    # Потолок числа аккаунтов: открытая регистрация не должна забить сервер базами
    max_users: int = 50

    # Redis: рейт-лимиты и очередь задач ИИ. Пусто — лимиты хранятся в памяти процесса.
    redis_url: Optional[str] = None
    rate_limit_enabled: bool = True
    # Брать IP клиента из X-Real-IP (его ставит Caddy перед backend). Без прокси — false.
    trust_proxy_headers: bool = False

    # Вложения к контактам: S3-совместимое хранилище (MinIO в docker compose, см. app/storage.py).
    # Без S3_ENDPOINT_URL — адреса AWS; ключи можно не задавать отдельно, если они те же, что у MinIO.
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("s3_access_key", "minio_root_user"))
    s3_secret_key: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("s3_secret_key", "minio_root_password")
    )
    s3_bucket: str = "personalcrm-attachments"
    s3_region: str = "us-east-1"
    attachment_max_mb: int = 25
    attachments_quota_mb: int = 500
    # ИИ-помощник (Sprint 6): OpenAI-совместимый API, по умолчанию — локальный Qwen в Ollama
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3.5:4b"
    llm_api_key: Optional[str] = None  # Ollama ключ не проверяет
    # Холодная загрузка модели в видеопамять — до минуты, поэтому таймаут с запасом
    llm_timeout_s: float = 180
    # Qwen 3.5 умеет «думать» — для разбора заметок это лишние секунды. Пусто — не передавать
    llm_reasoning_effort: str = "none"
    # Запасной провайдер, если локальная модель недоступна: "" (выключен) или "claude"
    llm_fallback: str = ""
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-haiku-5-5"

    # Очередь задач ИИ (arq поверх REDIS_URL)
    ai_concurrency: int = 1           # одновременных запросов к модели (GPU 8 ГБ — одна-две)
    ai_user_max_queued: int = 3       # задач одного пользователя в очереди и в работе
    ai_job_timeout_s: int = 240
    ai_job_max_tries: int = 2         # повтор только при недоступной модели
    ai_result_ttl_s: int = 6 * 3600   # сколько хранится результат (предпросмотр)
    ai_queue_expires_s: int = 15 * 60  # задача, не взятая в работу за это время, отменяется

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


def check_secrets(s: Settings) -> None:
    """
    Не запускаться с секретом по умолчанию: им подписаны JWT (подделка входа под любым
    пользователем), отпечатки паролей телефона и — без TOKEN_ENCRYPTION_KEY — ключ OAuth-токенов.
    Случайные значения создаёт scripts/init_env.py.
    """
    if s.secret_key == INSECURE_SECRET_KEY or len(s.secret_key) < SECRET_KEY_MIN_LENGTH:
        raise RuntimeError(
            f"SECRET_KEY не задан или короче {SECRET_KEY_MIN_LENGTH} символов. "
            "Создайте backend/.env: python scripts/init_env.py"
        )


# Singleton — импортировать отсюда
settings = Settings()
