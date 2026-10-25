"""
Телефоны: один номер — один ключ (89…, +7…, со скобками), поиск по номеру в API и у ИИ,
полная карточка для модели, миграция старых записей.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.ai import ask, tools
from app.db import get_db
from app.main import app
from app.models.contact import ContactCreate, ContactUpdate, Relationship
from app.repositories import contacts as contacts_repo
from app.services import phones
from tests.ai_fakes import FakeLLM

SAME_NUMBER = [
    "89215535333",
    "+79215535333",
    "79215535333",
    "9215535333",
    "8 (921) 553-53-33",
    "+7 921 553 53 33",
    "8-921-553-53-33",
]


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test_phones"]


async def _contact(db, **fields):
    return await contacts_repo.create_contact(db, ContactCreate(**fields))


class TestPhoneKey:
    @pytest.mark.parametrize("raw", SAME_NUMBER)
    def test_russian_variants_are_one_number(self, raw):
        assert phones.phone_key(raw) == "+79215535333"

    def test_foreign_number_keeps_its_country(self):
        assert phones.phone_key("+44 20 7946 0958") == "+442079460958"

    @pytest.mark.parametrize(("raw", "key"), [("112", "112"), ("553-53-33", "5535333"), ("", ""), ("нет", "")])
    def test_short_or_broken_numbers_become_digits(self, raw, key):
        # Не выдумываем +7 к служебным номерам и обрывкам
        assert phones.phone_key(raw) == key

    def test_same_phone(self):
        assert phones.same_phone("89215535333", "+7 (921) 553-53-33")
        assert not phones.same_phone("89215535333", "89215535334")
        assert not phones.same_phone("", "")

    @pytest.mark.parametrize(
        ("text", "found"),
        [
            ("8 (921) 553-53-33\n чей номер", ["+79215535333"]),
            ("позвони +7 921 553 53 33 или 89215535333", ["+79215535333"]),
            ("номер 553-53-33", ["5535333"]),
            ("сумма 1 500 000 руб", []),
            ("встреча в 2024 году", []),
            ("какой номер у ани", []),
        ],
    )
    def test_numbers_in_free_text(self, text, found):
        assert phones.find_in_text(text) == found


class TestContactModel:
    def test_normalized_is_computed_and_client_value_ignored(self):
        contact = ContactCreate(first_name="Аня", phones=[{"value": "89215535333", "normalized": "подделка"}])

        assert contact.phones[0].normalized == "+79215535333"
        assert contact.phones[0].value == "89215535333"

    def test_same_number_twice_is_kept_once(self):
        contact = ContactCreate(
            first_name="Аня",
            phones=[{"value": "89215535333", "label": "мобильный"}, {"value": "+7 921 553-53-33", "label": "рабочий"}],
        )

        assert [(p.value, p.label) for p in contact.phones] == [("89215535333", "мобильный")]

    def test_update_also_dedupes(self):
        update = ContactUpdate(phones=[{"value": "9215535333"}, {"value": "89215535333"}])

        assert len(update.phones) == 1


class TestApiSearch:
    @pytest.fixture
    def client(self, db):
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as c:
            resp = c.post("/api/auth/login", data={"username": "admin", "password": "admin-test-pass"})
            c.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
            yield c
        app.dependency_overrides.clear()

    @pytest.mark.parametrize("query", [*SAME_NUMBER, "553-53-33", "5535333"])
    def test_any_spelling_finds_the_contact(self, client, query):
        client.post("/api/contacts/", json={"first_name": "Анюта", "phones": [{"value": "8 (921) 553-53-33"}]})

        found = client.get("/api/contacts/", params={"q": query}).json()

        assert [c["first_name"] for c in found] == ["Анюта"]

    def test_other_number_does_not_match(self, client):
        client.post("/api/contacts/", json={"first_name": "Анюта", "phones": [{"value": "89215535333"}]})

        assert client.get("/api/contacts/", params={"q": "89215535334"}).json() == []


class TestAiSearchAndCard:
    @pytest.mark.parametrize("query", ["89215535333", "+7 921 553-53-33", "553-53-33"])
    async def test_search_by_phone(self, db, query):
        anna = await _contact(db, first_name="Анюта", phones=[{"value": "8 (921) 553-53-33"}])

        assert [c["id"] for c in await tools.search_contacts(db, query)] == [anna.id]

    async def test_search_by_email(self, db):
        anna = await _contact(db, first_name="Анюта", emails=[{"value": "anna.k@mail.ru"}])

        assert [c["id"] for c in await tools.search_contacts(db, "anna.k@mail.ru")] == [anna.id]

    async def test_card_has_phones_emails_relationships_priority(self, db):
        husband = await _contact(db, first_name="Борис")
        anna = await _contact(
            db,
            first_name="Анюта",
            phones=[{"value": "8 (921) 553-53-33", "label": "мобильный"}],
            emails=[{"value": "anna.k@mail.ru", "label": "личный"}],
            relationships=[Relationship(contact_id=husband.id, label="муж")],
            priority="high",
        )

        card = await tools.get_contact(db, anna.id)

        assert card["phones"] == [{"value": "8 (921) 553-53-33", "label": "мобильный"}]
        assert card["emails"] == [{"value": "anna.k@mail.ru", "label": "личный"}]
        assert card["relationships"] == [{"name": "Борис", "label": "муж"}]
        assert card["priority"] == "high"
        # Служебное модели не передаём
        assert not {"external_ids", "sync_hash", "sources", "dav_uid"} & card.keys()

    async def test_ask_finds_contact_by_number_the_model_dropped(self, db):
        anna = await _contact(db, first_name="Анюта", phones=[{"value": "8 (921) 553-53-33"}])

        def respond(schema_name: str, system: str, user: str) -> dict:
            if schema_name == "search_terms":
                return {"names": [], "keywords": []}  # модель номер потеряла
            context = json.loads(user.split("<контакты>\n", 1)[1].split("\n</контакты>", 1)[0])
            assert context[0]["phones"][0]["value"] == "8 (921) 553-53-33"
            return {"answer": "Это номер Анюты", "contact_ids": [anna.id]}

        result = await ask.run_ask(db, FakeLLM(respond), {"question": "89215535333 чей номер"})

        assert result["contacts"] == [{"id": anna.id, "name": "Анюта"}]


class TestAskByName:
    async def test_ask_about_anya_finds_anyuta_with_her_number(self, db):
        anna = await _contact(db, first_name="Анюта", phones=[{"value": "8 (921) 553-53-33"}])
        seen: list[dict] = []

        def respond(schema_name: str, system: str, user: str) -> dict:
            if schema_name == "search_terms":
                return {"names": ["Аня"], "keywords": []}
            seen.extend(json.loads(user.split("<контакты>\n", 1)[1].split("\n</контакты>", 1)[0]))
            return {"answer": "8 (921) 553-53-33", "contact_ids": [anna.id]}

        result = await ask.run_ask(db, FakeLLM(respond), {"question": "какой номер у ани"})

        assert [c["id"] for c in seen] == [anna.id]
        assert seen[0]["phones"] == [{"value": "8 (921) 553-53-33", "label": "телефон"}]
        assert result["contacts"] == [{"id": anna.id, "name": "Анюта"}]

    async def test_fallback_list_shows_phones(self, db):
        await _contact(db, first_name="Анюта", phones=[{"value": "8 (921) 553-53-33"}])

        context = await ask.collect_context(db, ["кто-то, кого нет"])

        assert context[0]["phones"] == ["8 (921) 553-53-33"]


class TestBackfill:
    async def test_old_contacts_get_keys_once(self, db):
        now = datetime.now(timezone.utc)
        await db["contacts"].insert_one(
            {"first_name": "Старая", "phones": [{"value": "89215535333", "label": "моб"}], "created_at": now, "updated_at": now}
        )

        assert await contacts_repo.backfill_phone_keys(db) == 1
        assert await contacts_repo.backfill_phone_keys(db) == 0

        doc = await db["contacts"].find_one({"first_name": "Старая"})
        assert doc["phones"] == [{"value": "89215535333", "label": "моб", "normalized": "+79215535333"}]
        # Дата изменения не тронута — синхронизация не увидит «правки»
        assert abs((doc["updated_at"].replace(tzinfo=None) - now.replace(tzinfo=None)).total_seconds()) < 0.01
        assert [c["id"] for c in await tools.search_contacts(db, "+7 921 553-53-33")] == [str(doc["_id"])]
