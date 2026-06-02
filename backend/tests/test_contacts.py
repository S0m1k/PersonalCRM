"""
Тесты модели контакта и репозитория CRUD.

Используем mongomock-motor для замены реального MongoDB in-memory базой,
поэтому тесты не требуют запущенного MongoDB.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from mongomock_motor import AsyncMongoMockClient

from app.models.contact import (
    ContactCreate,
    ContactUpdate,
    CustomField,
    Email,
    ExternalIds,
    Phone,
    Relationship,
)
from app.repositories import contacts as repo


# ---------------------------------------------------------------------------
# Фикстуры
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db():
    """In-memory MongoDB клиент на время теста."""
    client = AsyncMongoMockClient()
    yield client["test_crm"]


@pytest_asyncio.fixture
async def sample_contact(db):
    """Создаёт один контакт и возвращает его."""
    data = ContactCreate(
        first_name="Иван",
        last_name="Петров",
        phones=[Phone(value="+79001234567", label="мобильный")],
        emails=[Email(value="ivan@example.com", label="личный")],
        company="ООО Ромашка",
        position="Менеджер",
        city="Москва",
        birthday="1990-05-15",
        notes="Клиент с 2020 года",
        category="клиент",
        priority="high",
        custom_fields=[CustomField(key="Telegram", value="@ivan")],
        relationships=[],
        source="manual",
    )
    return await repo.create_contact(db, data)


# ---------------------------------------------------------------------------
# Тесты модели
# ---------------------------------------------------------------------------


class TestContactModels:
    def test_phone_defaults(self):
        p = Phone(value="+7999")
        assert p.label == "телефон"

    def test_email_defaults(self):
        e = Email(value="a@b.com")
        assert e.label == "email"

    def test_birthday_valid(self):
        c = ContactCreate(birthday="1985-03-15")
        assert c.birthday == "1985-03-15"

    def test_birthday_empty_string_becomes_none(self):
        c = ContactCreate(birthday="")
        assert c.birthday is None

    def test_birthday_none(self):
        c = ContactCreate(birthday=None)
        assert c.birthday is None

    def test_birthday_invalid_raises(self):
        with pytest.raises(Exception):
            ContactCreate(birthday="not-a-date")

    def test_contact_create_defaults(self):
        c = ContactCreate()
        assert c.first_name == ""
        assert c.phones == []
        assert c.emails == []
        assert c.source == "manual"
        assert c.sources == []

    def test_contact_update_all_optional(self):
        # Все поля опциональны — можно создать пустой
        u = ContactUpdate()
        dumped = u.model_dump(exclude_none=True)
        assert dumped == {}

    def test_contact_update_partial(self):
        u = ContactUpdate(first_name="Новое Имя", city="СПб")
        dumped = u.model_dump(exclude_none=True)
        assert dumped == {"first_name": "Новое Имя", "city": "СПб"}

    def test_external_ids_defaults(self):
        e = ExternalIds()
        assert e.outlook is None
        assert e.google is None
        assert e.telegram is None


# ---------------------------------------------------------------------------
# Тесты репозитория
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestContactRepository:
    async def test_create_and_get(self, db, sample_contact):
        """create → get_by_id должны вернуть тот же контакт."""
        fetched = await repo.get_contact_by_id(db, sample_contact.id)
        assert fetched is not None
        assert fetched.id == sample_contact.id
        assert fetched.first_name == "Иван"
        assert fetched.last_name == "Петров"
        assert fetched.company == "ООО Ромашка"

    async def test_get_invalid_id_returns_none(self, db):
        result = await repo.get_contact_by_id(db, "not-an-objectid")
        assert result is None

    async def test_get_missing_id_returns_none(self, db):
        from bson import ObjectId
        result = await repo.get_contact_by_id(db, str(ObjectId()))
        assert result is None

    async def test_list_all(self, db, sample_contact):
        contacts = await repo.list_contacts(db)
        assert len(contacts) >= 1
        ids = [c.id for c in contacts]
        assert sample_contact.id in ids

    async def test_list_search_by_name(self, db, sample_contact):
        results = await repo.list_contacts(db, q="Петров")
        assert any(c.id == sample_contact.id for c in results)

    async def test_list_search_by_company(self, db, sample_contact):
        results = await repo.list_contacts(db, q="Ромашка")
        assert any(c.id == sample_contact.id for c in results)

    async def test_list_search_by_email(self, db, sample_contact):
        results = await repo.list_contacts(db, q="ivan@example")
        assert any(c.id == sample_contact.id for c in results)

    async def test_list_search_by_phone(self, db, sample_contact):
        results = await repo.list_contacts(db, q="+7900")
        assert any(c.id == sample_contact.id for c in results)

    async def test_list_filter_category(self, db, sample_contact):
        results = await repo.list_contacts(db, category="клиент")
        assert any(c.id == sample_contact.id for c in results)

        results_miss = await repo.list_contacts(db, category="друг")
        assert not any(c.id == sample_contact.id for c in results_miss)

    async def test_list_filter_priority(self, db, sample_contact):
        results = await repo.list_contacts(db, priority="high")
        assert any(c.id == sample_contact.id for c in results)

    async def test_list_search_no_match(self, db, sample_contact):
        results = await repo.list_contacts(db, q="xXxNeverMatchxXx")
        assert not any(c.id == sample_contact.id for c in results)

    async def test_list_pagination(self, db):
        """Создаём несколько контактов и проверяем skip/limit."""
        for i in range(5):
            await repo.create_contact(db, ContactCreate(first_name=f"Test{i}"))

        page1 = await repo.list_contacts(db, skip=0, limit=3)
        page2 = await repo.list_contacts(db, skip=3, limit=3)
        assert len(page1) == 3
        # page2 может быть меньше 3 если всего записей мало — просто проверим непересечение
        ids1 = {c.id for c in page1}
        ids2 = {c.id for c in page2}
        assert ids1.isdisjoint(ids2)

    async def test_update_partial(self, db, sample_contact):
        """PATCH — обновляем только city и notes."""
        updated = await repo.update_contact(
            db,
            sample_contact.id,
            ContactUpdate(city="Санкт-Петербург", notes="Обновлено"),
        )
        assert updated is not None
        assert updated.city == "Санкт-Петербург"
        assert updated.notes == "Обновлено"
        # Остальные поля не тронуты
        assert updated.first_name == "Иван"
        assert updated.company == "ООО Ромашка"

    async def test_update_phones(self, db, sample_contact):
        new_phones = [
            Phone(value="+79009998877", label="рабочий"),
            Phone(value="+79001234567", label="мобильный"),
        ]
        updated = await repo.update_contact(
            db, sample_contact.id, ContactUpdate(phones=new_phones)
        )
        assert updated is not None
        assert len(updated.phones) == 2

    async def test_update_invalid_id_returns_none(self, db):
        result = await repo.update_contact(
            db, "bad-id", ContactUpdate(city="X")
        )
        assert result is None

    async def test_update_missing_id_returns_none(self, db):
        from bson import ObjectId
        result = await repo.update_contact(
            db, str(ObjectId()), ContactUpdate(city="X")
        )
        assert result is None

    async def test_update_empty_patch_returns_current(self, db, sample_contact):
        """Пустой PATCH не должен ломаться и вернуть текущее состояние."""
        result = await repo.update_contact(db, sample_contact.id, ContactUpdate())
        assert result is not None
        assert result.id == sample_contact.id

    async def test_delete(self, db, sample_contact):
        deleted = await repo.delete_contact(db, sample_contact.id)
        assert deleted is True
        # После удаления — не найти
        fetched = await repo.get_contact_by_id(db, sample_contact.id)
        assert fetched is None

    async def test_delete_invalid_id(self, db):
        result = await repo.delete_contact(db, "not-an-id")
        assert result is False

    async def test_delete_missing_id(self, db):
        from bson import ObjectId
        result = await repo.delete_contact(db, str(ObjectId()))
        assert result is False

    async def test_created_at_updated_at_set(self, db):
        c = await repo.create_contact(db, ContactCreate(first_name="Тест"))
        assert c.created_at is not None
        assert c.updated_at is not None

    async def test_updated_at_changes_on_update(self, db, sample_contact):
        import asyncio
        # Небольшая задержка чтобы updated_at успел измениться
        await asyncio.sleep(0.01)
        updated = await repo.update_contact(
            db, sample_contact.id, ContactUpdate(city="Казань")
        )
        assert updated is not None
        assert updated.updated_at >= sample_contact.updated_at

    async def test_sources_auto_filled(self, db):
        """При create с source='manual' sources должен содержать ['manual']."""
        c = await repo.create_contact(db, ContactCreate(source="manual"))
        assert "manual" in c.sources

    async def test_birthday_stored_and_returned(self, db):
        c = await repo.create_contact(
            db, ContactCreate(first_name="День", birthday="2000-01-01")
        )
        assert c.birthday == "2000-01-01"
