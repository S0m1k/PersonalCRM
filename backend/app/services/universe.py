"""
«Вселенная» сети: кластеризация контактов по сходству профиля (должность, компания, теги, описание, город).

Без внешних зависимостей: TF-IDF по словам + сферический k-means (косинус), детерминированный
(без случайности: одинаковые данные → одинаковая картинка). Раскладка — кластеры по кругу,
внутри кластера контакты по спирали: чем ближе к центру кластера по сходству, тем ближе к центру пятна.
Чистая логика без IO: документы приносит роутер.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable

from pydantic import BaseModel

MIN_PROFILED = 8
MAX_CLUSTERS = 8
KMEANS_ITERATIONS = 20
LABEL_TERMS = 2
MIN_TOKEN_LEN = 3
# Названия компании и должности важнее случайных слов из описания
FIELD_WEIGHTS = {"company": 3, "position": 2, "tags": 3, "city": 1, "description": 1}
GOLDEN_ANGLE = math.pi * (3 - math.sqrt(5))
RING_RADIUS = 1.0
SPREAD = 0.4  # радиус пятна кластера относительно радиуса кольца

_TOKEN_RE = re.compile(r"[^\W\d_]{3,}", re.UNICODE)
STOP_WORDS = frozenset(
    """
    the and for with from that this you your llc ltd inc corp company group
    это как для при или так что его она они наш наша наши без над под про уже все всё еще ещё
    ооо зао оао компания группа
    """.split()
)


class UniverseCluster(BaseModel):
    id: int
    label: str
    contact_ids: list[str]


class Point(BaseModel):
    x: float
    y: float


class Universe(BaseModel):
    # False — данных профиля мало (< MIN_PROFILED контактов), кластеров нет
    ready: bool
    required: int = MIN_PROFILED
    profiled: int = 0
    clusters: list[UniverseCluster] = []
    positions: dict[str, Point] = {}


def tokenize(text: str) -> list[str]:
    return [t for t in (m.lower() for m in _TOKEN_RE.findall(text or "")) if t not in STOP_WORDS and len(t) >= MIN_TOKEN_LEN]


def profile_terms(doc: dict) -> Counter:
    """Слова профиля с весами полей."""
    terms: Counter = Counter()
    for field, weight in FIELD_WEIGHTS.items():
        value = doc.get(field)
        text = " ".join(value) if isinstance(value, list) else (value or "")
        for token in tokenize(text):
            terms[token] += weight
    return terms


Vector = dict[str, float]


def _normalize(vec: Vector) -> Vector:
    norm = math.sqrt(sum(v * v for v in vec.values()))
    return {k: v / norm for k, v in vec.items()} if norm else {}


def tfidf(profiles: list[Counter]) -> list[Vector]:
    """TF-IDF (сглаженный idf), L2-нормированные разреженные векторы."""
    n = len(profiles)
    df: Counter = Counter()
    for terms in profiles:
        df.update(terms.keys())
    idf = {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}
    return [_normalize({t: (1 + math.log(c)) * idf[t] for t, c in terms.items()}) for terms in profiles]


def cosine(a: Vector, b: Vector) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _centroid(vectors: Iterable[Vector]) -> Vector:
    total: Vector = {}
    for vec in vectors:
        for k, v in vec.items():
            total[k] = total.get(k, 0.0) + v
    return _normalize(total)


def choose_k(n: int) -> int:
    return max(2, min(MAX_CLUSTERS, round(math.sqrt(n / 1.2))))


def _init_centers(vectors: list[Vector], k: int) -> list[Vector]:
    """Farthest-first: первый — самый «типичный» (ближе всех к общему центру), остальные — самые непохожие."""
    overall = _centroid(vectors)
    first = max(range(len(vectors)), key=lambda i: (cosine(vectors[i], overall), -i))
    chosen = [first]
    while len(chosen) < k:
        best = max(
            (i for i in range(len(vectors)) if i not in chosen),
            key=lambda i: (min(1 - cosine(vectors[i], vectors[c]) for c in chosen), -i),
        )
        chosen.append(best)
    return [vectors[i] for i in chosen]


def kmeans(vectors: list[Vector], k: int) -> list[int]:
    """Сферический k-means; возвращает номер кластера для каждого вектора."""
    centers = _init_centers(vectors, k)
    assign = [-1] * len(vectors)
    for _ in range(KMEANS_ITERATIONS):
        new_assign = [max(range(k), key=lambda c: (cosine(v, centers[c]), -c)) for v in vectors]
        if new_assign == assign:
            break
        assign = new_assign
        for c in range(k):
            members = [vectors[i] for i, a in enumerate(assign) if a == c]
            if members:
                centers[c] = _centroid(members)
    return assign


def cluster_label(centroid: Vector) -> str:
    top = sorted(centroid.items(), key=lambda kv: (-kv[1], kv[0]))[:LABEL_TERMS]
    return " · ".join(t.capitalize() for t, _ in top) or "Остальные"


def _layout(cluster_index: int, cluster_count: int, ranked: list[tuple[str, float]]) -> dict[str, Point]:
    """ranked — (id, сходство с центром кластера) по убыванию сходства."""
    angle = 2 * math.pi * cluster_index / cluster_count
    cx, cy = RING_RADIUS * math.cos(angle), RING_RADIUS * math.sin(angle)
    points: dict[str, Point] = {}
    for rank, (contact_id, similarity) in enumerate(ranked):
        # Радиус растёт с рангом (спираль Ферма); неспецифичные контакты уходят на край пятна
        r = SPREAD * math.sqrt((rank + 0.5) / len(ranked)) * (1.15 - 0.3 * similarity)
        theta = rank * GOLDEN_ANGLE + angle
        points[contact_id] = Point(x=round(cx + r * math.cos(theta), 4), y=round(cy + r * math.sin(theta), 4))
    return points


def build_universe(docs: list[dict], min_profiled: int = MIN_PROFILED) -> Universe:
    """docs — документы контактов с _id и полями профиля."""
    profiled = [(str(d["_id"]), profile_terms(d)) for d in docs]
    profiled = sorted(((cid, terms) for cid, terms in profiled if terms), key=lambda p: p[0])
    if len(profiled) < min_profiled:
        return Universe(ready=False, required=min_profiled, profiled=len(profiled))

    ids = [cid for cid, _ in profiled]
    vectors = tfidf([terms for _, terms in profiled])
    k = choose_k(len(ids))
    assign = kmeans(vectors, k)

    groups: dict[int, list[int]] = {}
    for index, cluster in enumerate(assign):
        groups.setdefault(cluster, []).append(index)
    ordered = sorted(groups.values(), key=lambda members: (-len(members), ids[members[0]]))

    clusters: list[UniverseCluster] = []
    positions: dict[str, Point] = {}
    for cluster_id, members in enumerate(ordered):
        centroid = _centroid(vectors[i] for i in members)
        ranked = sorted(((ids[i], cosine(vectors[i], centroid)) for i in members), key=lambda p: (-p[1], p[0]))
        clusters.append(
            UniverseCluster(id=cluster_id, label=cluster_label(centroid), contact_ids=[cid for cid, _ in ranked])
        )
        positions.update(_layout(cluster_id, len(ordered), ranked))
    return Universe(ready=True, required=min_profiled, profiled=len(ids), clusters=clusters, positions=positions)
