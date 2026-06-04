"""
Тесты парсеров импорта: vCard, CSV (Google export), Telegram JSON.
"""

from __future__ import annotations

from app.import_.parsers import (
    detect_format,
    parse_csv,
    parse_telegram_export,
    parse_vcard,
)


# ---------------------------------------------------------------------------
# vCard
# ---------------------------------------------------------------------------


class TestVCard:
    def test_basic_vcard(self):
        content = (
            "BEGIN:VCARD\n"
            "VERSION:3.0\n"
            "FN:Иван Петров\n"
            "TEL;TYPE=CELL:+7 900 123 45 67\n"
            "EMAIL:ivan@example.com\n"
            "ORG:Acme;Отдел продаж\n"
            "TITLE:Менеджер\n"
            "BDAY:1985-03-15\n"
            "NOTE:Важный клиент\n"
            "END:VCARD\n"
        )
        contacts = parse_vcard(content)
        assert len(contacts) == 1
        c = contacts[0]
        assert c["first_name"] == "Иван"
        assert c["last_name"] == "Петров"
        assert c["phones"][0]["value"] == "+7 900 123 45 67"
        assert c["phones"][0]["label"] == "мобильный"
        assert c["emails"][0]["value"] == "ivan@example.com"
        assert c["company"] == "Acme"
        assert c["position"] == "Менеджер"
        assert c["birthday"] == "1985-03-15"
        assert c["notes"] == "Важный клиент"
        assert c["source"] == "vcard"

    def test_vcard_yyyymmdd_birthday(self):
        content = "BEGIN:VCARD\nFN:A B\nBDAY:19850315\nEND:VCARD\n"
        c = parse_vcard(content)[0]
        assert c["birthday"] == "1985-03-15"

    def test_vcard_structured_name_only(self):
        content = "BEGIN:VCARD\nN:Петров;Иван;;;\nEND:VCARD\n"
        c = parse_vcard(content)[0]
        assert c["first_name"] == "Иван"
        assert c["last_name"] == "Петров"

    def test_vcard_skips_empty(self):
        content = "BEGIN:VCARD\nTEL:123\nEND:VCARD\n"
        # без имени контакт пропускается
        assert parse_vcard(content) == []

    def test_multiple_vcards(self):
        content = (
            "BEGIN:VCARD\nFN:A One\nEND:VCARD\n"
            "BEGIN:VCARD\nFN:B Two\nEND:VCARD\n"
        )
        assert len(parse_vcard(content)) == 2


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


class TestCSV:
    def test_google_export_format(self):
        content = (
            "Given Name,Family Name,E-mail 1 - Value,Phone 1 - Value,Organization 1 - Name\n"
            "Иван,Петров,ivan@example.com,+79001234567,Acme\n"
        )
        contacts = parse_csv(content)
        assert len(contacts) == 1
        c = contacts[0]
        assert c["first_name"] == "Иван"
        assert c["last_name"] == "Петров"
        assert c["emails"][0]["value"] == "ivan@example.com"
        assert c["phones"][0]["value"] == "+79001234567"
        assert c["company"] == "Acme"
        assert c["source"] == "csv"

    def test_russian_headers(self):
        content = "Имя,Фамилия,Телефон,Компания\nАнна,Смирнова,+79005554433,ООО Ромашка\n"
        c = parse_csv(content)[0]
        assert c["first_name"] == "Анна"
        assert c["last_name"] == "Смирнова"
        assert c["phones"][0]["value"] == "+79005554433"
        assert c["company"] == "ООО Ромашка"

    def test_skips_nameless_rows(self):
        content = "First Name,Last Name,Email\n,,nobody@example.com\nBob,,bob@example.com\n"
        contacts = parse_csv(content)
        assert len(contacts) == 1
        assert contacts[0]["first_name"] == "Bob"

    def test_date_normalization(self):
        content = "First Name,Birthday\nIvan,15.03.1985\n"
        assert parse_csv(content)[0]["birthday"] == "1985-03-15"


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------


class TestTelegram:
    def test_flat_list(self):
        content = (
            '[{"first_name":"Иван","last_name":"Петров","phone_number":"+79001234567"}]'
        )
        contacts = parse_telegram_export(content)
        assert len(contacts) == 1
        c = contacts[0]
        assert c["first_name"] == "Иван"
        assert c["phones"][0]["value"] == "+79001234567"
        assert c["phones"][0]["label"] == "telegram"
        assert c["source"] == "telegram"

    def test_nested_format(self):
        content = '{"contacts":{"list":[{"first_name":"Анна","phone_number":"123"}]}}'
        contacts = parse_telegram_export(content)
        assert len(contacts) == 1
        assert contacts[0]["first_name"] == "Анна"

    def test_skips_nameless(self):
        content = '[{"phone_number":"123"}]'
        assert parse_telegram_export(content) == []

    def test_invalid_json_raises(self):
        import pytest

        with pytest.raises(ValueError):
            parse_telegram_export("not json")


# ---------------------------------------------------------------------------
# detect_format
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_by_extension(self):
        assert detect_format("a.vcf", "BEGIN:VCARD") == "vcard"
        assert detect_format("a.csv", "x,y") == "csv"

    def test_telegram_json(self):
        assert detect_format("export.json", '[{"first_name":"A","phone_number":"1"}]') == "telegram"

    def test_vcard_by_content(self):
        assert detect_format("noext", "BEGIN:VCARD\nFN:X\nEND:VCARD") == "vcard"

    def test_unknown(self):
        assert detect_format("file.bin", "random bytes") == "unknown"
