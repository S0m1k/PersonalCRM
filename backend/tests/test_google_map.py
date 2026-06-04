"""
Тесты маппинга Google People API → модель CRM (map_google_to_crm).
"""

from __future__ import annotations

from app.models.contact import ContactCreate
from app.sync.google import is_deleted, map_google_to_crm


def test_full_contact_mapping():
    person = {
        "resourceName": "people/c123",
        "names": [{"givenName": "Иван", "familyName": "Петров"}],
        "phoneNumbers": [{"value": "+79001234567", "type": "mobile"}],
        "emailAddresses": [{"value": "ivan@example.com", "type": "home"}],
        "organizations": [{"name": "Acme", "title": "Менеджер"}],
        "birthdays": [{"date": {"year": 1985, "month": 3, "day": 15}}],
        "addresses": [{"city": "Москва"}],
        "biographies": [{"value": "Заметка"}],
    }
    c = map_google_to_crm(person)
    assert c["first_name"] == "Иван"
    assert c["last_name"] == "Петров"
    assert c["phones"][0]["value"] == "+79001234567"
    assert c["emails"][0]["value"] == "ivan@example.com"
    assert c["company"] == "Acme"
    assert c["position"] == "Менеджер"
    assert c["birthday"] == "1985-03-15"
    assert c["city"] == "Москва"
    assert c["notes"] == "Заметка"
    assert c["source"] == "google"
    assert c["external_ids"]["google"] == "people/c123"


def test_birthday_without_year():
    person = {
        "resourceName": "people/c1",
        "names": [{"givenName": "A"}],
        "birthdays": [{"date": {"month": 12, "day": 31}}],
    }
    c = map_google_to_crm(person)
    assert c["birthday"] == "1900-12-31"  # год по умолчанию


def test_minimal():
    c = map_google_to_crm({"resourceName": "people/x", "names": [{"givenName": "Анна"}]})
    assert c["first_name"] == "Анна"
    assert c["phones"] == []
    assert c["birthday"] is None


def test_is_deleted():
    assert is_deleted({"metadata": {"deleted": True}}) is True
    assert is_deleted({"metadata": {}}) is False
    assert is_deleted({}) is False


def test_output_validates_as_contact_create():
    person = {
        "resourceName": "people/c1",
        "names": [{"givenName": "Иван", "familyName": "П"}],
        "phoneNumbers": [{"value": "+79001234567", "type": "mobile"}],
    }
    contact = ContactCreate.model_validate(map_google_to_crm(person))
    assert contact.source == "google"
