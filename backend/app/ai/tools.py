"""
Инструменты ИИ над данными CRM — всегда над базой одного пользователя (db передаётся явно).

Те же функции понадобятся MCP-серверу (Sprint 9). Всё, что предлагает модель,
проходит через них: невалидное значение, чужой или несуществующий id → ToolError.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from ..models.contact import ContactCreate, ContactOut, ContactUpdate, CustomField, Email, Phone
from ..models.question import QuestionCreate, QuestionOut, QuestionUpdate
from ..models.template import FieldDef
from ..repositories import contacts as contacts_repo
from ..repositories import questions as questions_repo
from ..repositories import templates as templates_repo
from ..services import phones
from ..services.fields import FieldValidationError, validate_field_values

# Основные поля карточки, которые ИИ может менять (имя — только при создании контакта)
BASE_FIELDS: dict[str, str] = {
    "company": "Компания",
    "position": "Должность",
    "city": "Город",
    "birthday": "День рождения",
    "category": "Категория",
}
MAX_VALUE = 500
MAX_NOTE = 2000
NOTES_CONTEXT = 1500  # сколько последних символов заметок показывать модели
SEARCH_LIMIT = 5


# Семейства имён: полные формы и частые уменьшительные. Любое имя семейства находит остальные —
# поиск не должен зависеть от того, как записан контакт («Анюта») и как спросили («Аня», «Анна»)
NAME_FAMILIES: tuple[tuple[str, ...], ...] = (
    ("Александр", "Александра", "Саша", "Шура", "Саня"), ("Алексей", "Лёша", "Алёша", "Лёха"),
    ("Анатолий", "Толя"), ("Андрей", "Андрюша"), ("Анна", "Аня", "Анюта", "Анечка", "Нюра", "Нюша"),
    ("Анастасия", "Настя", "Настёна"), ("Артём", "Тёма"), ("Борис", "Боря"), ("Валентин", "Валентина", "Валя"),
    ("Василий", "Вася"), ("Вера", "Верочка"), ("Виктор", "Витя"), ("Виктория", "Вика"),
    ("Владимир", "Вова", "Володя"), ("Владислав", "Влад", "Слава"), ("Вячеслав", "Слава"), ("Ярослав", "Слава"),
    ("Галина", "Галя"), ("Георгий", "Гоша", "Жора"), ("Григорий", "Гриша"), ("Дарья", "Даша"),
    ("Дмитрий", "Дима", "Митя"), ("Евгений", "Евгения", "Женя"), ("Екатерина", "Катя"),
    ("Елена", "Лена", "Алёна"), ("Елизавета", "Лиза"), ("Иван", "Ваня"), ("Ирина", "Ира"),
    ("Константин", "Костя"), ("Ксения", "Ксюша"), ("Лев", "Лёва"), ("Любовь", "Люба"), ("Людмила", "Люда", "Мила"),
    ("Максим", "Макс"), ("Мария", "Маша", "Маруся"), ("Михаил", "Миша"), ("Надежда", "Надя"),
    ("Наталья", "Наталия", "Наташа"), ("Николай", "Коля"), ("Ольга", "Оля"), ("Павел", "Паша"), ("Пётр", "Петя"),
    ("Полина", "Поля"), ("Сергей", "Серёжа"), ("Светлана", "Света"), ("Софья", "София", "Соня"),
    ("Станислав", "Стас"), ("Татьяна", "Таня"), ("Юлия", "Юля"), ("Юрий", "Юра"),
)


def _name_key(name: str) -> str:
    return name.strip().lower().replace("ё", "е")


_NAME_INDEX: dict[str, list[str]] = {}
for _family in NAME_FAMILIES:
    for _name in _family:
        _NAME_INDEX.setdefault(_name_key(_name), []).extend(n for n in _family if n != _name)


_EMAIL_IN_TEXT = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def emails_in_text(text: str) -> list[str]:
    """Адреса почты из текста, в нижнем регистре, без повторов."""
    return list(dict.fromkeys(e.lower() for e in _EMAIL_IN_TEXT.findall(text)))


def contacts_in_text(text: str) -> list[str]:
    """
    Номера телефонов и email из текста — поисковые запросы, которые не нужно доверять
    модели: она их теряет или переписывает. Номер — сразу в виде ключа (+79215535333).
    """
    found = [*phones.find_in_text(text), *_EMAIL_IN_TEXT.findall(text)]
    return list(dict.fromkeys(found))


def name_variants(name: str) -> list[str]:
    """Другие имена того же семейства (Аня → Анна, Анюта, …); неизвестное имя — пусто."""
    return list(dict.fromkeys(_NAME_INDEX.get(_name_key(name), [])))


class ToolError(ValueError):
    """Действие нельзя выполнить: понятное пользователю сообщение."""


def full_name(contact: ContactOut) -> str:
    return " ".join(p for p in (contact.first_name, contact.last_name) if p).strip() or "Без имени"


def _fuzzy(term: str) -> str:
    """Регэксп для слова: е/ё не различаем, спецсимволы экранированы."""
    escaped = re.escape(term)
    return re.sub("[её]", "[её]", re.sub("[ЕЁ]", "[ЕЁ]", escaped))


_SEARCH_FIELDS = (
    "first_name", "last_name", "company", "city", "position", "emails.value", "custom_fields.value", "notes",
)


async def search_contacts(db: AsyncIOMotorDatabase, query: str, limit: int = SEARCH_LIMIT) -> list[dict]:
    """
    Контакты по запросу. Номер телефона (в любой записи: 8…, +7…, со скобками) ищется
    по ключу Phone.normalized; иначе — каждое слово запроса должно быть в одном из полей
    (имя, фамилия, компания, город, должность, email, свои поля, заметки).
    """
    phone_pattern = phones.search_pattern(query)
    if phone_pattern:
        mongo_query: dict[str, Any] = {"phones.normalized": {"$regex": phone_pattern}}
    else:
        terms = [t for t in re.split(r"\s+", query.strip()) if t][:4]
        if not terms:
            return []
        mongo_query = {
            "$and": [{"$or": [{f: {"$regex": _fuzzy(t), "$options": "i"}} for f in _SEARCH_FIELDS]} for t in terms]
        }
    docs = await db[contacts_repo.COLLECTION].find(mongo_query).limit(limit).to_list(length=limit)
    return [summary(ContactOut.from_mongo(d)) for d in docs]


def summary(contact: ContactOut) -> dict:
    return {
        "id": contact.id,
        "name": full_name(contact),
        "company": contact.company,
        "city": contact.city,
    }


async def _require_contact(db: AsyncIOMotorDatabase, contact_id: str) -> ContactOut:
    contact = await contacts_repo.get_contact_by_id(db, contact_id)
    if contact is None:
        raise ToolError("Контакт не найден")
    return contact


async def _template_defs(db: AsyncIOMotorDatabase, contact: Optional[ContactOut]) -> list[FieldDef]:
    if contact is None or not contact.template_id:
        return []
    template = await templates_repo.get_template(db, contact.template_id)
    return list(template.fields) if template else []


async def get_contact(db: AsyncIOMotorDatabase, contact_id: str) -> dict:
    """
    Карточка для модели — всё, что видит пользователь: поля с подписями (их ИИ может менять),
    телефоны, почта, связи и приоритет (только для чтения), открытые вопросы, хвост заметок.
    Служебное (id синхронизации, отпечатки, CardDAV) не передаём: модели оно не нужно.
    """
    contact = await _require_contact(db, contact_id)
    defs = await _template_defs(db, contact)
    questions = await questions_repo.list_questions(db, status="open", contact_id=contact_id, limit=20)
    fields: list[dict[str, Any]] = [
        {"key": key, "label": label, "value": getattr(contact, key) or ""} for key, label in BASE_FIELDS.items()
    ]
    fields += [
        {"key": d.key, "label": d.label, "type": d.type, "options": d.options, "value": contact.fields.get(d.key, "")}
        for d in defs
    ]
    fields += [{"key": cf.key, "label": cf.key, "value": cf.value} for cf in contact.custom_fields]
    return {
        "id": contact.id,
        "name": full_name(contact),
        "fields": fields,
        "phones": [{"value": p.value, "label": p.label} for p in contact.phones],
        "emails": [{"value": e.value, "label": e.label} for e in contact.emails],
        "relationships": await _relationships(db, contact),
        "priority": contact.priority,
        "open_questions": [{"id": q.id, "text": q.text} for q in questions],
        "notes": contact.notes[-NOTES_CONTEXT:],
    }


async def _relationships(db: AsyncIOMotorDatabase, contact: ContactOut) -> list[dict]:
    """Связи с другими контактами — с именами, а не id (одним запросом)."""
    if not contact.relationships:
        return []
    ids = [r.contact_id for r in contact.relationships]
    names = {
        c.id: full_name(c)
        for c in await contacts_repo.get_contacts_by_ids(db, ids)
    }
    return [{"name": names.get(r.contact_id, "?"), "label": r.label} for r in contact.relationships]


def _clean_value(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ToolError("Пустое значение")
    if len(text) > MAX_VALUE:
        raise ToolError(f"Значение длиннее {MAX_VALUE} символов")
    return text


async def describe_field(db: AsyncIOMotorDatabase, contact: Optional[ContactOut], key: str) -> tuple[str, str]:
    """(подпись поля, текущее значение) — для предпросмотра; contact=None — новый контакт."""
    if key in BASE_FIELDS:
        return BASE_FIELDS[key], str(getattr(contact, key) or "") if contact else ""
    if contact is None:
        return key, ""
    for d in await _template_defs(db, contact):
        if d.key == key:
            return d.label, str(contact.fields.get(key, ""))
    for cf in contact.custom_fields:
        if cf.key.lower() == key.lower():
            return cf.key, cf.value
    return key, ""


async def check_field(db: AsyncIOMotorDatabase, contact: Optional[ContactOut], key: str, value: Any) -> Any:
    """Нормализованное значение поля или ToolError (используется и в предпросмотре, и при записи)."""
    key = key.strip()
    if not key or len(key) > 60:
        raise ToolError("Некорректное название поля")
    text = _clean_value(value)
    if key == "birthday":
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise ToolError("День рождения — дата ГГГГ-ММ-ДД") from None
    if key in BASE_FIELDS:
        return text
    defs = await _template_defs(db, contact)
    if any(d.key == key for d in defs):
        try:
            return validate_field_values(defs, {key: text})[key]
        except FieldValidationError as exc:
            raise ToolError(str(exc)) from None
    return text


async def update_fields(db: AsyncIOMotorDatabase, contact_id: str, changes: dict[str, Any]) -> ContactOut:
    """
    Изменить поля: основные (город, компания…), поля шаблона по ключу,
    остальное — свои поля карточки (по названию, без учёта регистра).
    """
    contact = await _require_contact(db, contact_id)
    defs = await _template_defs(db, contact)
    template_keys = {d.key for d in defs}
    base: dict[str, Any] = {}
    typed = dict(contact.fields)
    custom = [CustomField(key=cf.key, value=cf.value) for cf in contact.custom_fields]
    for key, value in changes.items():
        normalized = await check_field(db, contact, key, value)
        if key in BASE_FIELDS:
            base[key] = normalized
        elif key in template_keys:
            typed[key] = normalized
        else:
            existing = next((i for i, cf in enumerate(custom) if cf.key.lower() == key.strip().lower()), None)
            if existing is None:
                custom = [*custom, CustomField(key=key.strip(), value=str(normalized))]
            else:
                custom = [
                    CustomField(key=cf.key, value=str(normalized)) if i == existing else cf
                    for i, cf in enumerate(custom)
                ]
    update = ContactUpdate(**base, fields=typed if defs else None, custom_fields=custom)
    updated = await contacts_repo.update_contact(db, contact_id, update)
    if updated is None:
        raise ToolError("Контакт не найден")
    return updated


async def add_phone(db: AsyncIOMotorDatabase, contact_id: str, value: str) -> ContactOut:
    """Добавить телефон в карточку; такой же номер (в любой записи) второй раз не добавляется."""
    contact = await _require_contact(db, contact_id)
    number = value.strip()
    if not number or len(number) > 50:
        raise ToolError("Некорректный номер телефона")
    if any(phones.same_phone(number, p.value) for p in contact.phones):
        return contact
    updated = await contacts_repo.update_contact(
        db, contact_id, ContactUpdate(phones=[*contact.phones, Phone(value=number, label="мобильный")])
    )
    if updated is None:
        raise ToolError("Контакт не найден")
    return updated


async def add_email(db: AsyncIOMotorDatabase, contact_id: str, value: str) -> ContactOut:
    """Добавить адрес почты в карточку; уже имеющийся (без учёта регистра) не дублируется."""
    contact = await _require_contact(db, contact_id)
    address = value.strip().lower()
    if not _EMAIL_IN_TEXT.fullmatch(address) or len(address) > 320:
        raise ToolError("Некорректный адрес почты")
    if any(e.value.strip().lower() == address for e in contact.emails):
        return contact
    updated = await contacts_repo.update_contact(
        db, contact_id, ContactUpdate(emails=[*contact.emails, Email(value=address, label="email")])
    )
    if updated is None:
        raise ToolError("Контакт не найден")
    return updated


async def add_note(db: AsyncIOMotorDatabase, contact_id: str, text: str, today: Optional[date] = None) -> ContactOut:
    """Дописать заметку в конец с датой."""
    contact = await _require_contact(db, contact_id)
    note = text.strip()
    if not note:
        raise ToolError("Пустая заметка")
    if len(note) > MAX_NOTE:
        raise ToolError(f"Заметка длиннее {MAX_NOTE} символов")
    entry = f"{(today or date.today()).isoformat()}: {note}"
    notes = f"{contact.notes.rstrip()}\n\n{entry}" if contact.notes.strip() else entry
    updated = await contacts_repo.update_contact(db, contact_id, ContactUpdate(notes=notes))
    if updated is None:
        raise ToolError("Контакт не найден")
    return updated


def _question_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ToolError("Пустой вопрос")
    if len(cleaned) > 500:
        raise ToolError("Вопрос длиннее 500 символов")
    return cleaned


async def add_question(
    db: AsyncIOMotorDatabase, contact_id: str, text: str, ask_at: Optional[str] = None
) -> QuestionOut:
    await _require_contact(db, contact_id)
    try:
        data = QuestionCreate(contact_id=contact_id, text=_question_text(text), ask_at=ask_at, source="ai")
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    return await questions_repo.create_question(db, data)


async def find_open_question(db: AsyncIOMotorDatabase, contact_id: str, question_id: str) -> Optional[QuestionOut]:
    questions = await questions_repo.list_questions(db, status="open", contact_id=contact_id)
    return next((q for q in questions if q.id == question_id), None)


async def answer_question(
    db: AsyncIOMotorDatabase,
    contact_id: str,
    answer: str,
    question_id: Optional[str] = None,
    question_text: str = "",
) -> QuestionOut:
    """
    Закрыть вопрос ответом. question_id — открытый вопрос этого контакта;
    без него вопрос создаётся сразу отвеченным (узнал то, что не успел записать как вопрос).
    """
    reply = answer.strip()
    if not reply:
        raise ToolError("Пустой ответ")
    if len(reply) > 5000:
        raise ToolError("Ответ длиннее 5000 символов")
    if question_id:
        if await find_open_question(db, contact_id, question_id) is None:
            raise ToolError("Открытый вопрос не найден")
    else:
        question_id = (await add_question(db, contact_id, question_text)).id
    updated = await questions_repo.update_question(
        db, question_id, QuestionUpdate(status="answered", answer=reply)
    )
    if updated is None:
        raise ToolError("Вопрос не найден")
    return updated


async def create_contact(db: AsyncIOMotorDatabase, first_name: str, last_name: str = "") -> ContactOut:
    first, last = first_name.strip()[:100], last_name.strip()[:100]
    if not first and not last:
        raise ToolError("Нужно имя нового контакта")
    return await contacts_repo.create_contact(
        db, ContactCreate(first_name=first, last_name=last, source="manual")
    )
