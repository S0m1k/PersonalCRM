"""
vCard 3.0 для CardDAV: запись контакта и чтение карточек с iPhone / Android.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.contact import ContactOut
from app.services.vcard import contact_to_vcard, vcard_to_fields


def _contact(**overrides) -> ContactOut:
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    data = {
        "id": "6ad7dc44345abcdd100168a2",
        "first_name": "Пётр",
        "last_name": "Иванов",
        "company": "ООО «Альфа»",
        "position": "Директор",
        "city": "Москва",
        "birthday": "1978-10-25",
        "notes": "Строка 1\nСтрока 2; с точкой с запятой, и запятой",
        "category": "партнёры",
        "phones": [{"value": "+7 916 123-45-67", "label": "мобильный"}, {"value": "+7 495 000-00-00", "label": "рабочий"}],
        "emails": [{"value": "petr@alfa.ru", "label": "рабочий"}],
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return ContactOut(**data)


class TestWrite:
    def test_contains_core_properties(self):
        card = contact_to_vcard(_contact())

        assert card.startswith("BEGIN:VCARD\r\nVERSION:3.0\r\n")
        assert card.endswith("END:VCARD\r\n")
        assert "UID:6ad7dc44345abcdd100168a2\r\n" in card
        assert "N:Иванов;Пётр;;;\r\n" in card
        assert "FN:Пётр Иванов\r\n" in card
        assert "ORG:ООО «Альфа»\r\n" in card
        assert "TITLE:Директор\r\n" in card
        assert "TEL;TYPE=CELL:+7 916 123-45-67\r\n" in card
        assert "TEL;TYPE=WORK:+7 495 000-00-00\r\n" in card
        assert "EMAIL;TYPE=INTERNET,WORK:petr@alfa.ru\r\n" in card
        assert "ADR;TYPE=HOME:;;;Москва;;;\r\n" in card
        assert "BDAY:1978-10-25\r\n" in card
        assert "CATEGORIES:партнёры\r\n" in card

    def test_special_characters_are_escaped(self):
        card = contact_to_vcard(_contact())

        assert "NOTE:Строка 1\\nСтрока 2\\; с точкой с запятой\\, и запятой" in card.replace("\r\n ", "")

    def test_long_lines_are_folded_to_75_octets(self):
        card = contact_to_vcard(_contact(notes="ж" * 200))

        assert all(len(line.encode()) <= 75 for line in card.split("\r\n"))

    def test_client_uid_is_kept(self):
        card = contact_to_vcard(_contact(), uid="ABC-123-FROM-IPHONE")

        assert "UID:ABC-123-FROM-IPHONE\r\n" in card

    def test_roundtrip(self):
        fields = vcard_to_fields(contact_to_vcard(_contact()))

        assert fields["first_name"] == "Пётр"
        assert fields["last_name"] == "Иванов"
        assert fields["notes"] == "Строка 1\nСтрока 2; с точкой с запятой, и запятой"
        assert fields["phones"] == [
            {"value": "+7 916 123-45-67", "label": "мобильный"},
            {"value": "+7 495 000-00-00", "label": "рабочий"},
        ]
        assert fields["emails"] == [{"value": "petr@alfa.ru", "label": "рабочий"}]
        assert fields["city"] == "Москва"
        assert fields["birthday"] == "1978-10-25"
        assert fields["category"] == "партнёры"


IPHONE_CARD = (
    "BEGIN:VCARD\r\n"
    "VERSION:3.0\r\n"
    "PRODID:-//Apple Inc.//iPhone OS 18.0//EN\r\n"
    "N:Козлова;Анна;Сергеевна;;\r\n"
    "FN:Анна Сергеевна Козлова\r\n"
    "ORG:Студия «Лето»;Дизайн\r\n"
    "item1.EMAIL;type=INTERNET;type=pref:anna@leto.ru\r\n"
    "item1.X-ABLabel:_$!<Other>!$_\r\n"
    "TEL;type=CELL;type=VOICE;type=pref:+7 (921) 555-12-12\r\n"
    "TEL;type=HOME;type=VOICE:+7 812 111-22-33\r\n"
    "item2.ADR;type=HOME;type=pref:;;Невский 1;Санкт-Петербург;;191025;Россия\r\n"
    "NOTE:Подруга жены\\, познакомились в 2019\\nлюбит джаз\r\n"
    "BDAY;VALUE=date:1985-10-21\r\n"
    "UID:4E3F2A10-1111-2222-3333-444455556666\r\n"
    "END:VCARD\r\n"
)


class TestRead:
    def test_iphone_card(self):
        fields = vcard_to_fields(IPHONE_CARD)

        assert fields["first_name"] == "Анна"
        assert fields["last_name"] == "Козлова"
        assert fields["company"] == "Студия «Лето»"
        assert fields["emails"] == [{"value": "anna@leto.ru", "label": "email"}]
        assert fields["phones"] == [
            {"value": "+7 (921) 555-12-12", "label": "мобильный"},
            {"value": "+7 812 111-22-33", "label": "домашний"},
        ]
        assert fields["city"] == "Санкт-Петербург"
        assert fields["notes"] == "Подруга жены, познакомились в 2019\nлюбит джаз"
        assert fields["birthday"] == "1985-10-21"

    def test_folded_lines_are_joined(self):
        card = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Олег\r\nNOTE:начало \r\n продолжение\r\nEND:VCARD\r\n"

        assert vcard_to_fields(card)["notes"] == "начало продолжение"

    def test_fn_only_is_split(self):
        card = "BEGIN:VCARD\nVERSION:3.0\nFN:Сергей Титов\nEND:VCARD\n"

        fields = vcard_to_fields(card)

        assert (fields["first_name"], fields["last_name"]) == ("Сергей", "Титов")

    def test_birthday_without_year(self):
        card = "BEGIN:VCARD\nVERSION:3.0\nFN:Олег\nBDAY:--10-25\nEND:VCARD\n"

        assert vcard_to_fields(card)["birthday"] == "1604-10-25"

    def test_missing_fields_are_cleared(self):
        """Удалил телефон на iPhone — в CRM он тоже должен исчезнуть."""
        card = "BEGIN:VCARD\nVERSION:3.0\nFN:Олег\nEND:VCARD\n"

        fields = vcard_to_fields(card)

        assert fields["phones"] == []
        assert fields["emails"] == []
        assert fields["company"] == ""
        assert fields["birthday"] is None

    def test_uid_is_returned_separately(self):
        from app.services.vcard import vcard_uid

        assert vcard_uid(IPHONE_CARD) == "4E3F2A10-1111-2222-3333-444455556666"
