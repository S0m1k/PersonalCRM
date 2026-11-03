"""
Роутер графа: GET /api/network — узлы-контакты и рёбра (связи из карточек + совместные взаимодействия).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..auth import get_current_user, get_user_db
from ..models.user import User
from ..repositories import contacts as contacts_repo
from ..repositories import interactions as interactions_repo
from ..services.network import NODE_LIMIT, NetworkGraph, build_graph

router = APIRouter(prefix="/api/network", tags=["network"])

DbDep = Annotated[AsyncIOMotorDatabase, Depends(get_user_db)]
AuthDep = Annotated[User, Depends(get_current_user)]

_PROJECTION = {
    "first_name": 1,
    "last_name": 1,
    "company": 1,
    "group_ids": 1,
    "tags": 1,
    "importance": 1,
    "relationships": 1,
}


@router.get("", response_model=NetworkGraph, summary="Граф связей")
async def network(
    db: DbDep,
    _user: AuthDep,
    min_weight: int = Query(default=1, ge=1, description="Минимум совместных взаимодействий для ребра «together»"),
) -> NetworkGraph:
    collection = db[contacts_repo.COLLECTION]
    total = await collection.count_documents({})
    docs = (
        await collection.find({}, _PROJECTION)
        .sort([("importance", -1), ("updated_at", -1)])
        .limit(NODE_LIMIT)
        .to_list(length=NODE_LIMIT)
    )
    shared = await interactions_repo.shared_contact_groups(db)
    return build_graph(docs, docs, shared, min_weight=min_weight, truncated=total > NODE_LIMIT)
