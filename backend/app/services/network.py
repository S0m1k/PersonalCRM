"""
Граф связей для экрана «Сеть».

Узлы — контакты, рёбра двух видов:
  relationship — связь из карточки (Relationship), label — характер отношений;
  together     — люди участвовали в одном взаимодействии или прошедшем событии, weight — сколько раз.
Чистая логика без IO: документы приносит роутер.
"""

from __future__ import annotations

from itertools import combinations
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, Field

NODE_LIMIT = 500


class NetworkNode(BaseModel):
    id: str
    name: str
    company: str = ""
    group_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    importance: Optional[int] = None


class NetworkEdge(BaseModel):
    source: str
    target: str
    kind: Literal["relationship", "together"]
    label: str = ""
    weight: int = 1


class NetworkGraph(BaseModel):
    nodes: list[NetworkNode]
    edges: list[NetworkEdge]
    # Контактов больше лимита — показаны самые важные
    truncated: bool = False


def _name(doc: dict) -> str:
    return " ".join(p for p in (doc.get("first_name", ""), doc.get("last_name", "")) if p).strip() or "Без имени"


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def relationship_edges(docs: Iterable[dict], node_ids: set[str]) -> list[NetworkEdge]:
    """Связи из карточек; A→B и B→A — одно ребро (берём первую непустую подпись)."""
    labels: dict[tuple[str, str], str] = {}
    for doc in docs:
        source = str(doc["_id"])
        for rel in doc.get("relationships") or []:
            target = rel.get("contact_id", "")
            if target == source or target not in node_ids or source not in node_ids:
                continue
            key = _pair(source, target)
            labels[key] = labels.get(key) or rel.get("label", "")
    return [NetworkEdge(source=a, target=b, kind="relationship", label=lbl) for (a, b), lbl in labels.items()]


def together_edges(groups: Iterable[list[str]], node_ids: set[str], min_weight: int) -> list[NetworkEdge]:
    """groups — списки людей одного взаимодействия / события. Пары считаются, вес = число совместных."""
    counts: dict[tuple[str, str], int] = {}
    for ids in groups:
        present = sorted({i for i in ids if i in node_ids})
        for a, b in combinations(present, 2):
            counts[(a, b)] = counts.get((a, b), 0) + 1
    return [
        NetworkEdge(source=a, target=b, kind="together", weight=n)
        for (a, b), n in sorted(counts.items(), key=lambda kv: -kv[1])
        if n >= min_weight
    ]


def build_graph(
    contact_docs: list[dict],
    relationship_docs: list[dict],
    shared_groups: Iterable[list[str]],
    min_weight: int = 1,
    truncated: bool = False,
) -> NetworkGraph:
    nodes = [
        NetworkNode(
            id=str(d["_id"]),
            name=_name(d),
            company=d.get("company", ""),
            group_ids=list(d.get("group_ids") or []),
            tags=list(d.get("tags") or []),
            importance=d.get("importance"),
        )
        for d in contact_docs
    ]
    node_ids = {n.id for n in nodes}
    edges = relationship_edges(relationship_docs, node_ids) + together_edges(shared_groups, node_ids, min_weight)
    return NetworkGraph(nodes=nodes, edges=edges, truncated=truncated)
