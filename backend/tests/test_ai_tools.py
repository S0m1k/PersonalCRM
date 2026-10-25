"""
Инструменты ИИ над базой пользователя: поиск, поля, заметки, вопросы.
"""

from __future__ import annotations

from datetime import date

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.ai import tools
from app.ai.tools import ToolError
from app.models.contact import ContactCreate, CustomField
from app.models.template import TemplateCreate
from app.repositories import contacts as contacts_repo
from app.repositories import questions as questions_repo
from app.repositories import templates as templates_repo


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test_ai_tools"]


async def _contact(db, **fields):
    return await contacts_repo.create_contact(db, ContactCreate(**fields))


class TestSearch:
    async def test_e_and_yo_are_the_same(self, db):
        petr = await _contact(db, first_name="Пётр", last_name="Смирнов")

        assert [c["id"] for c in await tools.search_contacts(db, "петр")] == [petr.id]
        assert [c["id"] for c in await tools.search_contacts(db, "ПЁТР смирнов")] == [petr.id]

    async def test_every_word_must_match(self, db):
        await _contact(db, first_name="Пётр", last_name="Смирнов")

        assert await tools.search_contacts(db, "Пётр Козлов") == []

    async def test_searches_city_company_custom_fields(self, db):
        anna = await _contact(db, first_name="Анна", city="Дубай", custom_fields=[CustomField(key="Хобби", value="яхты")])

        assert [c["name"] for c in await tools.search_contacts(db, "дубай")] == ["Анна"]
        assert [c["id"] for c in await tools.search_contacts(db, "яхты")] == [anna.id]

    async def test_regex_is_escaped(self, db):
        await _contact(db, first_name="Анна")

        assert await tools.search_contacts(db, ".*") == []
        assert await tools.search_contacts(db, "   ") == []


class TestFields:
    async def test_base_and_custom_fields(self, db):
        petr = await _contact(db, first_name="Пётр", custom_fields=[CustomField(key="Дети", value="сын")])

        updated = await tools.update_fields(db, petr.id, {"city": "Дубай", "дети": "сын, дочь 5 лет", "Хобби": "теннис"})

        assert updated.city == "Дубай"
        assert [(cf.key, cf.value) for cf in updated.custom_fields] == [("Дети", "сын, дочь 5 лет"), ("Хобби", "теннис")]

    async def test_template_field_is_validated(self, db):
        template = await templates_repo.create_template(
            db, TemplateCreate(name="Клиент", fields=[{"key": "budget", "label": "Бюджет", "type": "number"}])
        )
        petr = await _contact(db, first_name="Пётр", template_id=template.id)

        updated = await tools.update_fields(db, petr.id, {"budget": "1 500"})

        assert updated.fields == {"budget": 1500}
        with pytest.raises(ToolError, match="Бюджет"):
            await tools.update_fields(db, petr.id, {"budget": "много"})

    async def test_birthday_must_be_iso_date(self, db):
        petr = await _contact(db, first_name="Пётр")

        assert (await tools.update_fields(db, petr.id, {"birthday": "1990-05-01"})).birthday == "1990-05-01"
        with pytest.raises(ToolError):
            await tools.update_fields(db, petr.id, {"birthday": "весной"})

    async def test_unknown_contact(self, db):
        with pytest.raises(ToolError):
            await tools.update_fields(db, "000000000000000000000000", {"city": "Дубай"})
        with pytest.raises(ToolError):
            await tools.get_contact(db, "не-id")


class TestNotesAndQuestions:
    async def test_note_is_appended_with_date(self, db):
        petr = await _contact(db, first_name="Пётр", notes="Старое")

        updated = await tools.add_note(db, petr.id, "Встретились", today=date(2026, 10, 25))

        assert updated.notes == "Старое\n\n2026-10-25: Встретились"

    async def test_answer_open_question(self, db):
        petr = await _contact(db, first_name="Пётр")
        question = await tools.add_question(db, petr.id, "Как переезд?")

        answered = await tools.answer_question(db, petr.id, "Уже в Дубае", question_id=question.id)

        assert (answered.id, answered.status, answered.source) == (question.id, "answered", "ai")

    async def test_answer_creates_closed_question(self, db):
        petr = await _contact(db, first_name="Пётр")

        answered = await tools.answer_question(db, petr.id, "5 лет", question_text="Сколько лет дочке?")

        assert (answered.text, answered.answer, answered.status) == ("Сколько лет дочке?", "5 лет", "answered")

    async def test_question_of_another_contact_is_rejected(self, db):
        petr = await _contact(db, first_name="Пётр")
        anna = await _contact(db, first_name="Анна")
        question = await tools.add_question(db, anna.id, "Как дела?")

        with pytest.raises(ToolError):
            await tools.answer_question(db, petr.id, "Хорошо", question_id=question.id)
        assert (await questions_repo.list_questions(db, status="open"))[0].id == question.id

    async def test_get_contact_lists_open_questions_only(self, db):
        petr = await _contact(db, first_name="Пётр", city="Москва")
        await tools.add_question(db, petr.id, "Открытый")
        await tools.answer_question(db, petr.id, "да", question_text="Закрытый")

        card = await tools.get_contact(db, petr.id)

        assert [q["text"] for q in card["open_questions"]] == ["Открытый"]
        assert {"key": "city", "label": "Город", "value": "Москва"} in card["fields"]


class TestNames:
    def test_nickname_variants(self):
        assert tools.name_variants("Петя") == ["Пётр"]
        assert tools.name_variants(" саша ")[:2] == ["Александр", "Александра"]
        # В обе стороны и между уменьшительными: «Аня» найдёт контакт «Анюта»
        assert tools.name_variants("Пётр") == ["Петя"]
        assert "Анюта" in tools.name_variants("Аня")
        assert "Аня" in tools.name_variants("анюта")
        assert tools.name_variants("Зоя") == []

    async def test_capture_finds_contact_by_nickname_and_surname(self, db):
        from app.ai.capture import find_candidates

        kolya = await _contact(db, first_name="Николай", last_name="Зайцев")
        await _contact(db, first_name="Николай", last_name="Петров")

        # Модель ошиблась с полным именем — находим по словарю и по фамилии
        found = await find_candidates(db, {"mention": "Коля", "first_name": "Алексей", "last_name": "Зайцев"})

        assert found[0]["id"] == kolya.id
