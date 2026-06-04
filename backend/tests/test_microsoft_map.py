"""
Тесты маппинга Microsoft Graph → модель CRM (map_outlook_to_crm).
"""

from __future__ import annotations

from app.models.contact import ContactCreate
from app.sync.microsoft import map_outlook_to_crm


def test_full_contact_mapping():
    graph = {
        "id": "AAMkAGI2",
        "givenName": "Иван",
        "surname": "Петров",
        "mobilePhone": "+7 900 123 45 67",
        "businessPhones": ["+7 495 000 00 00"],
        "emailAddresses": [{"address": "ivan@example.com", "name": "Ivan"}],
        "companyName": "Acme",
        "jobTitle": "Менеджер",
        "birthday": "1985-03-15T00:00:00Z",
        "personalNotes": "VIP",
        "businessAddress": {"city": "Москва"},
    }
    c = map_outlook_to_crm(graph)
    assert c["first_name"] == "Иван"
    assert c["last_name"] == "Петров"
    assert {"value": "+7 900 123 45 67", "label": "мобильный"} in c["phones"]
    assert {"value": "+7 495 000 00 00", "label": "рабочий"} in c["phones"]
    assert c["emails"][0]["value"] == "ivan@example.com"
    assert c["company"] == "Acme"
    assert c["position"] == "Менеджер"
    assert c["birthday"] == "1985-03-15"  # обрезано до даты
    assert c["city"] == "Москва"
    assert c["notes"] == "VIP"
    assert c["source"] == "outlook"
    assert c["external_ids"]["outlook"] == "AAMkAGI2"


def test_minimal_contact():
    c = map_outlook_to_crm({"id": "x", "givenName": "Анна"})
    assert c["first_name"] == "Анна"
    assert c["last_name"] == ""
    assert c["phones"] == []
    assert c["emails"] == []
    assert c["birthday"] is None
    assert c["city"] == ""


def test_home_address_fallback():
    c = map_outlook_to_crm({"id": "x", "givenName": "A", "homeAddress": {"city": "Тверь"}})
    assert c["city"] == "Тверь"


def test_skips_empty_email_address():
    c = map_outlook_to_crm({"id": "x", "givenName": "A", "emailAddresses": [{"address": ""}]})
    assert c["emails"] == []


def test_output_validates_as_contact_create():
    """Результат маппинга должен проходить валидацию ContactCreate."""
    graph = {
        "id": "x",
        "givenName": "Иван",
        "surname": "Петров",
        "mobilePhone": "+79001234567",
        "emailAddresses": [{"address": "a@b.com", "name": "x"}],
        "birthday": "1990-01-01T00:00:00Z",
    }
    mapped = map_outlook_to_crm(graph)
    contact = ContactCreate.model_validate(mapped)  # не должно бросить
    assert contact.first_name == "Иван"
    assert contact.source == "outlook"
