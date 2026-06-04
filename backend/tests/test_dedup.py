"""
Тесты движка дедупликации: normalize_phone, find_duplicates, merge_contacts.
"""

from __future__ import annotations

from app.sync.dedup import find_duplicates, merge_contacts, normalize_phone


# ---------------------------------------------------------------------------
# normalize_phone
# ---------------------------------------------------------------------------


class TestNormalizePhone:
    def test_strips_formatting(self):
        assert normalize_phone("+7 (900) 123-45-67") == "79001234567"

    def test_russian_8_to_7(self):
        assert normalize_phone("8-900-123-45-67") == "79001234567"

    def test_8_and_plus7_equal(self):
        assert normalize_phone("89001234567") == normalize_phone("+79001234567")

    def test_empty(self):
        assert normalize_phone("") == ""


# ---------------------------------------------------------------------------
# find_duplicates
# ---------------------------------------------------------------------------


def _contact(**kw) -> dict:
    base = {
        "first_name": "",
        "last_name": "",
        "phones": [],
        "emails": [],
        "company": "",
    }
    base.update(kw)
    return base


class TestFindDuplicates:
    def test_phone_match_auto_merge(self):
        new = _contact(first_name="Иван", phones=[{"value": "+79001234567", "label": "m"}])
        existing = [
            _contact(
                id="1",
                first_name="Ваня",
                phones=[{"value": "89001234567", "label": "m"}],
            )
        ]
        matches = find_duplicates(new, existing)
        assert len(matches) == 1
        assert matches[0]["score"] >= 90
        assert matches[0]["action"] == "auto_merge"
        assert "совпадение телефона" in matches[0]["reasons"]

    def test_email_match(self):
        new = _contact(emails=[{"value": "A@Example.com", "label": "e"}])
        existing = [_contact(id="1", emails=[{"value": "a@example.com", "label": "e"}])]
        matches = find_duplicates(new, existing)
        assert matches and matches[0]["score"] >= 90

    def test_fuzzy_name_only_is_suggest(self):
        new = _contact(first_name="Александр", last_name="Иванов")
        existing = [_contact(id="1", first_name="Александр", last_name="Иванов")]
        matches = find_duplicates(new, existing)
        # только имя совпадает (70) → suggest_merge, не auto
        assert matches
        assert matches[0]["action"] == "suggest_merge"
        assert 70 <= matches[0]["score"] < 90

    def test_company_boost(self):
        new = _contact(first_name="Иван", last_name="П", company="Acme")
        existing = [_contact(id="1", first_name="Иван", last_name="П", company="Acme")]
        matches = find_duplicates(new, existing)
        # имя (70) + компания (20) = 90 → auto_merge
        assert matches[0]["score"] >= 90

    def test_no_match_below_threshold(self):
        new = _contact(first_name="Иван", company="X")
        existing = [_contact(id="1", first_name="Пётр", company="Y")]
        assert find_duplicates(new, existing) == []

    def test_sorted_by_score(self):
        new = _contact(
            first_name="Иван",
            phones=[{"value": "111", "label": "m"}],
            emails=[{"value": "i@x.com", "label": "e"}],
        )
        existing = [
            _contact(id="weak", first_name="Иван"),  # name only
            _contact(id="strong", phones=[{"value": "111", "label": "m"}]),  # phone
        ]
        matches = find_duplicates(new, existing)
        assert matches[0]["existing_contact"]["id"] == "strong"


# ---------------------------------------------------------------------------
# merge_contacts
# ---------------------------------------------------------------------------


class TestMergeContacts:
    def test_unions_phones_dedup(self):
        primary = _contact(phones=[{"value": "+79001234567", "label": "m"}])
        secondary = _contact(
            phones=[
                {"value": "89001234567", "label": "m"},  # тот же номер — не дублируем
                {"value": "+79990000000", "label": "w"},  # новый
            ]
        )
        merged = merge_contacts(primary, secondary)
        assert len(merged["phones"]) == 2

    def test_fills_empty_fields(self):
        primary = _contact(first_name="Иван", company="")
        secondary = _contact(company="Acme", position="CEO", city="Москва")
        merged = merge_contacts(primary, secondary)
        assert merged["company"] == "Acme"
        assert merged["position"] == "CEO"
        assert merged["city"] == "Москва"

    def test_does_not_overwrite_existing(self):
        primary = _contact(company="Original")
        secondary = _contact(company="Other")
        merged = merge_contacts(primary, secondary)
        assert merged["company"] == "Original"

    def test_merges_external_ids(self):
        primary = _contact(external_ids={"outlook": "o1", "google": None, "telegram": None})
        secondary = _contact(external_ids={"outlook": None, "google": "g1", "telegram": None})
        merged = merge_contacts(primary, secondary)
        assert merged["external_ids"]["outlook"] == "o1"
        assert merged["external_ids"]["google"] == "g1"

    def test_does_not_mutate_inputs(self):
        primary = _contact(phones=[{"value": "1", "label": "m"}])
        secondary = _contact(phones=[{"value": "2", "label": "m"}])
        merge_contacts(primary, secondary)
        assert len(primary["phones"]) == 1  # не изменился
