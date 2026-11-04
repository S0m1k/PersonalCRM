"""
Демо-данные для проверки интерфейса на ОТДЕЛЬНОМ тестовом стеке (не на рабочей базе!).

    python scripts/seed_demo.py --api http://localhost:8100

Создаёт пользователя demo@example.test (пароль — DEMO_PASSWORD ниже, только для локального теста),
~30 контактов с компаниями, городами, координатами, тегами, группами, приоритетами, частотой,
связями, взаимодействиями за последние 10 месяцев и прошедшими встречами. Повторный запуск
на той же базе добавит дубли — запускайте на чистом стеке.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone

DEMO_EMAIL = "demo@example.test"
DEMO_PASSWORD = "demo-password-2026"  # тестовый пароль для локального стека, не секрет

CITIES = {
    "Москва": (55.7558, 37.6173),
    "Санкт-Петербург": (59.9343, 30.3351),
    "Казань": (55.7963, 49.1088),
    "Дубай": (25.2048, 55.2708),
    "Тбилиси": (41.7151, 44.8271),
    "Белград": (44.7866, 20.4489),
    "Лиссабон": (38.7223, -9.1393),
    "Новосибирск": (55.0084, 82.9357),
}

PEOPLE = [
    ("Анна", "Смирнова", "Яндекс", "Продакт-менеджер", "Москва", ["продукт", "ментор"], "top"),
    ("Дмитрий", "Волков", "Яндекс", "Тимлид бэкенда", "Москва", ["инженер"], "high"),
    ("Мария", "Кузнецова", "Сбер", "Дизайнер", "Москва", ["дизайн"], "medium"),
    ("Сергей", "Морозов", "Сбер", "CTO", "Москва", ["инженер", "фаундер"], "top"),
    ("Елена", "Попова", "Ozon", "HR-директор", "Москва", ["найм"], "medium"),
    ("Алексей", "Лебедев", "Ozon", "Аналитик", "Санкт-Петербург", ["данные"], "low"),
    ("Ольга", "Новикова", "JetBrains", "Разработчик", "Белград", ["инженер"], "medium"),
    ("Павел", "Козлов", "JetBrains", "Деврел", "Белград", ["сообщество"], "high"),
    ("Наталья", "Соколова", "Тинькофф", "Маркетолог", "Москва", ["маркетинг"], "low"),
    ("Иван", "Павлов", "Тинькофф", "Инвестор", "Дубай", ["инвестор", "фаундер"], "top"),
    ("Татьяна", "Семёнова", "", "Психолог", "Тбилиси", ["здоровье"], "high"),
    ("Михаил", "Голубев", "Avito", "Руководитель продукта", "Москва", ["продукт"], "medium"),
    ("Юлия", "Виноградова", "Avito", "Дизайнер", "Казань", ["дизайн"], "low"),
    ("Андрей", "Богданов", "Kaspersky", "Безопасник", "Москва", ["инженер"], "none"),
    ("Ксения", "Воробьёва", "", "Фотограф", "Лиссабон", ["хобби"], "medium"),
    ("Николай", "Фёдоров", "Wildberries", "COO", "Москва", ["фаундер"], "high"),
    ("Светлана", "Михайлова", "Wildberries", "Юрист", "Москва", ["юрист"], "low"),
    ("Артём", "Беляев", "", "Тренер", "Москва", ["здоровье", "спорт"], "medium"),
    ("Виктория", "Тарасова", "VK", "Редактор", "Санкт-Петербург", ["медиа"], "low"),
    ("Максим", "Белов", "VK", "Разработчик", "Санкт-Петербург", ["инженер"], ""),
    ("Дарья", "Комарова", "", "Сестра", "Москва", ["семья"], "top"),
    ("Пётр", "Орлов", "", "Отец", "Новосибирск", ["семья"], "top"),
    ("Екатерина", "Киселева", "Skyeng", "Методист", "Казань", ["образование"], ""),
    ("Роман", "Макаров", "Skyeng", "CEO", "Дубай", ["фаундер", "инвестор"], "high"),
    ("Алина", "Андреева", "", "Подруга со школы", "Москва", ["друзья"], "high"),
    ("Глеб", "Ковалёв", "", "Сосед", "Москва", ["друзья"], ""),
    ("Вера", "Ильина", "MTS", "Партнёр", "Москва", ["партнёр"], "medium"),
    ("Олег", "Гусев", "MTS", "Закупки", "Москва", [], ""),
    ("Лиза", "Титова", "", "Однокурсница", "Тбилиси", ["друзья"], "low"),
    ("Станислав", "Кузьмин", "Касперский", "Архитектор", "Белград", ["инженер"], ""),
]

GROUPS = [("Коллеги", "💼"), ("Семья", "🏡"), ("Друзья", "🎉"), ("Нетворкинг", "🤝")]
AREAS = {
    "семья": ["Семья"], "друзья": ["Друзья"], "здоровье": ["Здоровье"], "спорт": ["Здоровье"],
    "хобби": ["Хобби и отдых"], "сообщество": ["Сообщество"], "образование": ["Развитие"],
}
FREQ = {"top": 14, "high": 30, "medium": 90, "low": 180, "none": None, "": None}
KINDS = ["note", "call", "meeting", "message", "email"]
TITLES = {
    "note": "Заметка после разговора", "call": "Созвонились", "meeting": "Кофе",
    "message": "Переписка в Telegram", "email": "Письмо",
}


def call(api: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{api}{path}", data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        sys.exit(f"{method} {path} → {exc.code}: {exc.read().decode(errors='replace')[:500]}")


def login(api: str) -> str:
    creds = {"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "name": "Демо"}
    req = urllib.request.Request(f"{api}/api/auth/register", data=json.dumps(creds).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            sys.exit(f"register → {exc.code}: {exc.read().decode(errors='replace')[:300]}")
    return call(api, "POST", "/api/auth/login/json", body={"username": DEMO_EMAIL, "password": DEMO_PASSWORD})[
        "access_token"
    ]


def seed(api: str) -> None:
    rnd = random.Random(42)
    token = login(api)
    groups = {name: call(api, "POST", "/api/groups", token, {"name": name, "emoji": emoji})["id"] for name, emoji in GROUPS}
    today = date.today()
    ids: list[str] = []
    for i, (first, last, company, position, city, tags, priority) in enumerate(PEOPLE):
        lat, lng = CITIES[city]
        group_ids = []
        if "семья" in tags:
            group_ids.append(groups["Семья"])
        elif "друзья" in tags:
            group_ids.append(groups["Друзья"])
        elif company:
            group_ids.append(groups["Коллеги" if i % 3 else "Нетворкинг"])
        body = {
            "first_name": first, "last_name": last, "company": company, "position": position, "city": city,
            "address": city, "tags": tags, "group_ids": group_ids, "priority": priority,
            "description": f"{position}{' в ' + company if company else ''}. Познакомились в {2015 + i % 10} году.",
            "location": {"lat": lat + rnd.uniform(-0.05, 0.05), "lng": lng + rnd.uniform(-0.05, 0.05), "label": city},
            "keep_in_touch": {"frequency_days": FREQ[priority]},
            "importance": rnd.randint(1, 5), "closeness": rnd.randint(1, 5),
            "life_areas": sorted({a for t in tags for a in AREAS.get(t, [])}) or (["Работа и карьера"] if company else []),
            "birthday": (date(1975 + i, 1 + (i * 5) % 12, 1 + (i * 7) % 28)).isoformat(),
            "first_met_at": (today - timedelta(days=400 + i * 90)).isoformat(),
            "emails": [{"value": f"{first.lower()}.{i}@example.test", "label": "рабочий"}] if company else [],
            "social": {"telegram": f"@demo_{i}"} if i % 2 else {},
            "source": "manual",
        }
        ids.append(call(api, "POST", "/api/contacts/", token, body)["id"])

    # Связи: коллеги по компании
    by_company: dict[str, list[str]] = {}
    for cid, person in zip(ids, PEOPLE):
        if person[2]:
            by_company.setdefault(person[2], []).append(cid)
    for members in by_company.values():
        if len(members) >= 2:
            call(api, "PATCH", f"/api/contacts/{members[0]}", token,
                 {"relationships": [{"contact_id": m, "label": "коллега"} for m in members[1:]]})

    seed_activity(api, token, ids, rnd)
    print(f"Готово: {len(ids)} контактов, {len(groups)} группы. Вход: {DEMO_EMAIL}")


def seed_activity(api: str, token: str, ids: list[str], rnd: random.Random) -> None:
    """Взаимодействия за ~10 месяцев (у приоритетных — чаще, часть — совместные) и встречи в календаре."""
    count = 0
    for cid, person in zip(ids, PEOPLE):
        n = {"top": 9, "high": 6, "medium": 3, "low": 1}.get(person[6], 0)
        for _ in range(n):
            kind = rnd.choice(KINDS)
            people = [cid] + ([rnd.choice(ids)] if rnd.random() < 0.25 else [])
            when = datetime.now(timezone.utc) - timedelta(days=rnd.randint(1, 300), hours=rnd.randint(0, 12))
            call(api, "POST", "/api/interactions", token, {
                "contact_ids": sorted(set(people)), "kind": kind, "title": TITLES[kind],
                "body": f"Обсудили планы, {person[3].lower()}.", "occurred_at": when.isoformat(),
            })
            count += 1
    # Несколько прошедших и будущих встреч в календаре
    for days in (-40, -12, -3, 0, 2, 9):
        start = (datetime.now(timezone.utc) + timedelta(days=days)).replace(hour=9, minute=0, second=0, microsecond=0)
        call(api, "POST", "/api/calendar/events", token, {
            "title": "Встреча" if days else "Обед сегодня", "start": start.isoformat(),
            "end": (start + timedelta(hours=1)).isoformat(), "contact_ids": rnd.sample(ids, 2),
        })
    print(f"Взаимодействий: {count}, встреч: 6")


def activity_only(api: str) -> None:
    """Догрузить только активность к уже созданным демо-контактам (если прошлый запуск оборвался)."""
    token = login(api)
    items = call(api, "GET", "/api/contacts/?limit=200", token)
    items = items["items"] if isinstance(items, dict) else items
    by_name = {(c["first_name"], c["last_name"]): c["id"] for c in items}
    ids = [by_name[(p[0], p[1])] for p in PEOPLE if (p[0], p[1]) in by_name]
    seed_activity(api, token, ids, random.Random(7))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("--api", default="http://localhost:8100", help="адрес backend тестового стека")
    parser.add_argument("--activity-only", action="store_true", help="только взаимодействия и встречи")
    args = parser.parse_args()
    if args.api.rstrip("/").endswith(":8000"):
        sys.exit("Похоже на рабочий backend (:8000). Демо-данные — только на отдельный тестовый стек.")
    (activity_only if args.activity_only else seed)(args.api.rstrip("/"))
