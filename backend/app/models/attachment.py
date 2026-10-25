"""
Pydantic-модели вложений к контактам (метаданные; сами файлы — в S3, см. app/storage.py).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, field_validator


class AttachmentOut(BaseModel):
    id: str
    contact_id: str
    file_name: str
    size: int
    content_type: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        # mongomock / MongoDB отдают naive-время в UTC
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    @classmethod
    def from_mongo(cls, doc: dict) -> "AttachmentOut":
        return cls(
            id=str(doc["_id"]),
            contact_id=doc["contact_id"],
            file_name=doc["file_name"],
            size=doc["size"],
            content_type=doc["content_type"],
            created_at=doc["created_at"],
        )


class AttachmentUsage(BaseModel):
    used: int
    quota: int
    max_file_size: int
