"""
Pydantic v2 модели для sync_connections и sync_log.

Коллекции MongoDB:
  - sync_connections  — учётные данные OAuth и состояние синхронизации
  - sync_log          — аудит-лог операций синхронизации
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# SyncConnection
# ---------------------------------------------------------------------------


class SyncConnection(BaseModel):
    """Документ коллекции sync_connections."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="ID (строка ObjectId)")

    provider: str = Field(..., description='"microsoft" | "google" | "apple"')

    # Токены хранятся зашифрованными через crypto.encrypt / crypto.decrypt
    access_token_enc: str = Field(..., description="Зашифрованный access_token")
    refresh_token_enc: Optional[str] = Field(
        default=None, description="Зашифрованный refresh_token (если есть)"
    )
    token_expires_at: Optional[datetime] = Field(
        default=None, description="Когда истекает access_token (UTC)"
    )

    # Что синхронизируем
    sync_contacts: bool = Field(default=True)
    sync_calendar: bool = Field(default=False)

    # Состояние инкрементального sync
    contacts_delta_link: Optional[str] = Field(
        default=None, description="Microsoft Graph delta-link для следующего инкрементального sync"
    )
    contacts_sync_token: Optional[str] = Field(
        default=None, description="Google syncToken для следующего sync"
    )
    contacts_last_sync: Optional[datetime] = None
    calendar_last_sync: Optional[datetime] = None

    # Webhooks (Sprint 3)
    webhook_subscription_id: Optional[str] = None
    webhook_expires_at: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_mongo(cls, doc: dict) -> "SyncConnection":
        data = dict(doc)
        data["id"] = str(data.pop("_id"))
        for ts_field in (
            "token_expires_at",
            "contacts_last_sync",
            "calendar_last_sync",
            "webhook_expires_at",
            "created_at",
            "updated_at",
        ):
            val = data.get(ts_field)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts_field] = val.replace(tzinfo=timezone.utc)
        return cls(**data)


class SyncConnectionOut(BaseModel):
    """
    Публичное представление подключения (без зашифрованных токенов).
    Используется в API-ответах.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    provider: str
    sync_contacts: bool
    sync_calendar: bool
    contacts_last_sync: Optional[datetime] = None
    calendar_last_sync: Optional[datetime] = None
    token_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_connection(cls, conn: SyncConnection) -> "SyncConnectionOut":
        return cls(
            id=conn.id,
            provider=conn.provider,
            sync_contacts=conn.sync_contacts,
            sync_calendar=conn.sync_calendar,
            contacts_last_sync=conn.contacts_last_sync,
            calendar_last_sync=conn.calendar_last_sync,
            token_expires_at=conn.token_expires_at,
            created_at=conn.created_at,
            updated_at=conn.updated_at,
        )


# ---------------------------------------------------------------------------
# SyncLog
# ---------------------------------------------------------------------------


class SyncStats(BaseModel):
    created: int = 0
    updated: int = 0
    deleted: int = 0
    merged: int = 0
    skipped: int = 0
    errors: int = 0


class SyncError(BaseModel):
    contact_name: str = ""
    error: str = ""


class SyncLog(BaseModel):
    """Документ коллекции sync_log."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="ID (строка ObjectId)")
    connection_id: str = Field(..., description="ID связанного SyncConnection")
    type: str = Field(..., description='"contacts" | "calendar"')
    action: str = Field(
        ..., description='"full_sync" | "delta_sync" | "import" | "push" | "webhook"'
    )
    stats: SyncStats = Field(default_factory=SyncStats)
    errors: list[SyncError] = Field(default_factory=list)
    started_at: datetime
    completed_at: Optional[datetime] = None

    @classmethod
    def from_mongo(cls, doc: dict) -> "SyncLog":
        data = dict(doc)
        data["id"] = str(data.pop("_id"))
        for ts_field in ("started_at", "completed_at"):
            val = data.get(ts_field)
            if isinstance(val, datetime) and val.tzinfo is None:
                data[ts_field] = val.replace(tzinfo=timezone.utc)
        if isinstance(data.get("stats"), dict):
            data["stats"] = SyncStats(**data["stats"])
        if data.get("errors"):
            data["errors"] = [
                SyncError(**e) if isinstance(e, dict) else e for e in data["errors"]
            ]
        return cls(**data)
