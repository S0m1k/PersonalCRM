"""
Роутер импорта контактов из файлов: /api/import/*

Поток:
  POST /api/import/upload            — загрузить файл (CSV/vCard/Telegram JSON),
                                       распарсить, сохранить во временную сессию
  GET  /api/import/{id}/preview      — превью: классификация каждого контакта
                                       (new / auto_merge / suggest_merge) против базы
  POST /api/import/{id}/confirm      — применить импорт (создать новые / слить дубли)

Сессии импорта хранятся во временной коллекции import_sessions, чтобы
распарсенные данные пережили шаг между preview и confirm.

Все маршруты защищены JWT (get_current_user).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..db import get_db
from ..models.contact import ContactCreate, ContactUpdate
from ..repositories import contacts as contacts_repo
from ..repositories import sync as sync_repo
from ..import_.parsers import (
    detect_format,
    parse_csv,
    parse_telegram_export,
    parse_vcard,
)
from ..sync.dedup import find_duplicates, merge_contacts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/import", tags=["import"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_db)]
AuthDep = Annotated[str, Depends(get_current_user)]

SESSION_COLLECTION = "import_sessions"

# Порог максимального количества контактов в одном файле (защита от перегруза)
MAX_CONTACTS = 5000


# ---------------------------------------------------------------------------
# Модели запросов / ответов
# ---------------------------------------------------------------------------


class ImportUploadResult(BaseModel):
    import_id: str
    format: str
    count: int


class PreviewMatch(BaseModel):
    existing_id: str
    name: str
    score: int
    reasons: list[str]


class PreviewItem(BaseModel):
    index: int
    contact: dict
    classification: str  # "new" | "auto_merge" | "suggest_merge"
    best_match: Optional[PreviewMatch] = None


class ImportPreview(BaseModel):
    import_id: str
    total: int
    new_count: int
    auto_merge_count: int
    suggest_count: int
    items: list[PreviewItem]


class ImportDecision(BaseModel):
    index: int
    action: str = Field(..., description='"create" | "merge" | "skip"')
    existing_id: Optional[str] = Field(
        default=None, description="ID существующего контакта при action=merge"
    )


class ImportConfirmRequest(BaseModel):
    decisions: list[ImportDecision] = Field(
        default_factory=list,
        description=(
            "Явные решения по индексам. Для не указанных применяется поведение "
            "по умолчанию: auto_merge → merge, suggest_merge → skip, new → create."
        ),
    )


class ImportConfirmResult(BaseModel):
    created: int
    merged: int
    skipped: int


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------


def _parse_oid(id_str: str) -> Optional[ObjectId]:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        return None


def _parse_content(fmt: str, content: str) -> list[dict]:
    if fmt == "vcard":
        return parse_vcard(content)
    if fmt == "csv":
        return parse_csv(content)
    if fmt == "telegram":
        return parse_telegram_export(content)
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Неподдерживаемый или неопознанный формат файла: {fmt!r}",
    )


def _display_name(contact: dict) -> str:
    return (
        f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        or "(без имени)"
    )


async def _load_session(db: AsyncIOMotorDatabase, import_id: str) -> dict:
    oid = _parse_oid(import_id)
    if oid is None:
        raise HTTPException(status_code=404, detail="Сессия импорта не найдена")
    doc = await db[SESSION_COLLECTION].find_one({"_id": oid})
    if doc is None:
        raise HTTPException(status_code=404, detail="Сессия импорта не найдена")
    return doc


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.post(
    "/upload",
    response_model=ImportUploadResult,
    summary="Загрузить файл контактов",
)
async def upload_file(
    db: DbDep,
    _user: AuthDep,
    file: UploadFile = File(...),
) -> ImportUploadResult:
    """Принять файл, распарсить и сохранить распарсенные контакты в сессию."""
    raw = await file.read()
    try:
        content = raw.decode("utf-8-sig")  # utf-8-sig снимает BOM, если есть
    except UnicodeDecodeError:
        try:
            content = raw.decode("cp1251")  # частый случай для русских CSV из Windows
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Не удалось прочитать файл: неподдерживаемая кодировка",
            )

    fmt = detect_format(file.filename or "", content)
    parsed = _parse_content(fmt, content)

    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="В файле не найдено контактов с именем",
        )
    if len(parsed) > MAX_CONTACTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Слишком много контактов ({len(parsed)}). Максимум {MAX_CONTACTS}.",
        )

    session_doc = {
        "format": fmt,
        "filename": file.filename,
        "parsed": parsed,
        "created_at": datetime.now(timezone.utc),
    }
    result = await db[SESSION_COLLECTION].insert_one(session_doc)

    return ImportUploadResult(
        import_id=str(result.inserted_id),
        format=fmt,
        count=len(parsed),
    )


@router.get(
    "/{import_id}/preview",
    response_model=ImportPreview,
    summary="Превью импорта с классификацией дублей",
)
async def preview_import(
    import_id: str,
    db: DbDep,
    _user: AuthDep,
) -> ImportPreview:
    """
    Классифицировать каждый распарсенный контакт против существующей базы:
      - auto_merge   (score ≥ 90): будет автоматически слит
      - suggest_merge (70–89): требует решения пользователя
      - new          (нет дублей): будет создан как новый
    """
    session = await _load_session(db, import_id)
    parsed: list[dict] = session.get("parsed", [])

    existing = await contacts_repo.list_contacts(db, limit=MAX_CONTACTS)
    existing_dicts = [c.model_dump() for c in existing]

    items: list[PreviewItem] = []
    new_count = auto_count = suggest_count = 0

    for idx, contact in enumerate(parsed):
        duplicates = find_duplicates(contact, existing_dicts)

        if duplicates:
            top = duplicates[0]
            classification = top["action"]  # "auto_merge" | "suggest_merge"
            best = top["existing_contact"]
            best_match = PreviewMatch(
                existing_id=best.get("id", ""),
                name=_display_name(best),
                score=top["score"],
                reasons=top["reasons"],
            )
        else:
            classification = "new"
            best_match = None

        if classification == "auto_merge":
            auto_count += 1
        elif classification == "suggest_merge":
            suggest_count += 1
        else:
            new_count += 1

        items.append(
            PreviewItem(
                index=idx,
                contact=contact,
                classification=classification,
                best_match=best_match,
            )
        )

    return ImportPreview(
        import_id=import_id,
        total=len(parsed),
        new_count=new_count,
        auto_merge_count=auto_count,
        suggest_count=suggest_count,
        items=items,
    )


@router.post(
    "/{import_id}/confirm",
    response_model=ImportConfirmResult,
    summary="Подтвердить и применить импорт",
)
async def confirm_import(
    import_id: str,
    db: DbDep,
    _user: AuthDep,
    body: Optional[ImportConfirmRequest] = None,
) -> ImportConfirmResult:
    """
    Применить импорт.

    Для каждого распарсенного контакта:
      - если есть явное решение (decisions) — выполняем его;
      - иначе поведение по умолчанию на основе классификации:
          auto_merge   → merge в лучший существующий контакт
          suggest_merge → skip (пользователь должен решить явно)
          new          → create
    """
    session = await _load_session(db, import_id)
    parsed: list[dict] = session.get("parsed", [])

    decisions_by_index: dict[int, ImportDecision] = {}
    if body and body.decisions:
        decisions_by_index = {d.index: d for d in body.decisions}

    existing = await contacts_repo.list_contacts(db, limit=MAX_CONTACTS)
    existing_dicts = [c.model_dump() for c in existing]
    existing_by_id = {c["id"]: c for c in existing_dicts}

    created = merged = skipped = 0

    for idx, contact in enumerate(parsed):
        decision = decisions_by_index.get(idx)

        # Определяем действие и целевой существующий контакт
        if decision is not None:
            action = decision.action
            target_id = decision.existing_id
        else:
            duplicates = find_duplicates(contact, existing_dicts)
            if duplicates and duplicates[0]["action"] == "auto_merge":
                action = "merge"
                target_id = duplicates[0]["existing_contact"].get("id")
            elif duplicates and duplicates[0]["action"] == "suggest_merge":
                action = "skip"  # неоднозначные дубли по умолчанию пропускаем
                target_id = None
            else:
                action = "create"
                target_id = None

        if action == "skip":
            skipped += 1
            continue

        if action == "merge" and target_id and target_id in existing_by_id:
            base = existing_by_id[target_id]
            merged_data = merge_contacts(base, contact)
            update = ContactUpdate.model_validate(
                {
                    k: v
                    for k, v in merged_data.items()
                    if k not in ("id", "created_at", "updated_at", "source")
                }
            )
            await contacts_repo.update_contact(db, target_id, update)
            existing_by_id[target_id] = merged_data
            merged += 1
        else:
            # create (или merge с несуществующим target → создаём как новый)
            create_data = ContactCreate.model_validate(contact)
            new_c = await contacts_repo.create_contact(db, create_data)
            new_dict = new_c.model_dump()
            existing_dicts.append(new_dict)
            existing_by_id[new_dict["id"]] = new_dict
            created += 1

    # Лог импорта (для истории на странице /sync)
    from ..models.sync import SyncStats

    await sync_repo.create_log(
        db,
        connection_id="import",
        type="contacts",
        action="import",
        stats=SyncStats(created=created, merged=merged, skipped=skipped),
        completed_at=datetime.now(timezone.utc),
    )

    # Сессию импорта можно удалить — она больше не нужна
    oid = _parse_oid(import_id)
    if oid is not None:
        await db[SESSION_COLLECTION].delete_one({"_id": oid})

    return ImportConfirmResult(created=created, merged=merged, skipped=skipped)
