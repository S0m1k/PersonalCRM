"""
Роутер целей и стратегий: /api/goals.

GET состояние + каталог подходов, PUT настройки, GET /metrics, GET /recommendations (следующие шаги),
POST /apply/preview и /apply, PUT /assignments (круги Данбара).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pydantic import ValidationError

from ..auth import get_current_user, get_user_db
from ..models.goals import ApplyBody, AssignmentsUpdate, GoalsUpdate, validate_settings
from ..models.user import User
from ..repositories import goals as repo
from ..services import strategy

router = APIRouter(prefix="/api/goals", tags=["goals"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

PERIODS = (30, 90, 180)


def _public(state: dict) -> dict[str, Any]:
    return {
        "primary": state["primary"],
        "enabled": state["enabled"],
        "settings": state["settings"],
        "assignments": state["assignments"],
        "updated_at": state["updated_at"],
        "catalogue": strategy.catalogue(),
    }


@router.get("", summary="Состояние целей и каталог подходов")
async def get_goals(db: DbDep, _user: AuthDep) -> dict[str, Any]:
    return _public(await repo.get_state(db))


@router.put("", summary="Выбрать подходы и сохранить настройки")
async def put_goals(data: GoalsUpdate, db: DbDep, _user: AuthDep) -> dict[str, Any]:
    state = await repo.get_state(db)
    changes: dict[str, Any] = {}
    primary = None if data.clear_primary else (data.primary or state["primary"])
    if data.primary or data.clear_primary:
        changes["primary"] = primary
    enabled = data.enabled if data.enabled is not None else state["enabled"]
    changes["enabled"] = [a for i, a in enumerate(enabled) if a != primary and a not in enabled[:i]]
    if data.settings:
        merged = dict(state["settings"])
        for approach, raw in data.settings.items():
            try:
                merged[approach] = validate_settings(approach, raw)
            except ValidationError as exc:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors(include_url=False, include_context=False)) from None
        changes["settings"] = merged
    return _public(await repo.save_state(db, changes))


@router.get("/metrics", summary="Метрики выполнения основного и дополнительных подходов")
async def get_metrics(
    db: DbDep, _user: AuthDep, period: Annotated[int, Query(description="30, 90 или 180 дней")] = 30
) -> dict[str, Any]:
    if period not in PERIODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="period: 30, 90 или 180")
    state = await repo.get_state(db)
    return strategy.compute_all_metrics(state, await repo.metrics_context(db, state, period))


@router.get("/recommendations", summary="Следующие шаги: кому написать сейчас")
async def get_recommendations(
    db: DbDep, _user: AuthDep, limit: Annotated[int, Query(ge=1, le=50)] = strategy.NEXT_STEPS_LIMIT
) -> dict[str, Any]:
    state = await repo.get_state(db)
    now = datetime.now(timezone.utc)
    contacts = await repo.load_contacts(db, now)
    return {"primary": state["primary"], "items": strategy.next_steps(state, contacts, now, limit)}


@router.post("/apply/preview", summary="Что изменится при применении стратегии к контактам")
async def apply_preview(db: DbDep, _user: AuthDep, data: ApplyBody | None = None) -> dict[str, Any]:
    state = await repo.get_state(db)
    return strategy.preview_apply(state, await repo.load_contacts(db), (data or ApplyBody()).overwrite)


@router.post("/apply", summary="Применить рекомендованные частоты к контактам")
async def apply(db: DbDep, _user: AuthDep, data: ApplyBody | None = None) -> dict[str, Any]:
    state = await repo.get_state(db)
    preview = strategy.preview_apply(state, await repo.load_contacts(db), (data or ApplyBody()).overwrite)
    frequencies = {i["contact_id"]: i["recommended"] for i in preview["items"] if i["action"] == "change"}
    changed = await repo.apply_frequencies(db, frequencies)
    # Теперь эти частоты поставила стратегия — их можно обновлять без «перезаписать»
    applied = {**state["applied"], **frequencies}
    await repo.save_state(db, {"applied": applied})
    return {"changed": changed, "skipped_manual": preview["skipped_manual"], "unchanged": preview["unchanged"]}


@router.put("/assignments", summary="Назначить контактам круги Данбара (пакетно)")
async def put_assignments(data: AssignmentsUpdate, db: DbDep, _user: AuthDep) -> dict[str, Any]:
    known = await repo.existing_contact_ids(db, list(data.assignments))
    unknown = sorted(set(data.assignments) - known)
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Контакты не найдены: {', '.join(unknown[:5])}")
    state = await repo.get_state(db)
    assignments = dict(state["assignments"])
    for cid, circle in data.assignments.items():
        if circle is None:
            assignments.pop(cid, None)
        else:
            assignments[cid] = {"circle": circle}
    return _public(await repo.save_state(db, {"assignments": assignments}))
