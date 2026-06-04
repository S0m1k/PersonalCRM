"""
Движок синхронизации Google People API (контакты).

Функции:
  - fetch_google_contacts   — полный pull всех контактов (+ requestSyncToken)
  - sync_google_contacts    — инкрементальный pull через syncToken
  - map_google_to_crm       — маппинг People API → модель CRM

HTTP-вызовы изолированы в _people_get_page для мокирования в тестах.
Используем REST напрямую через httpx (без google-api-python-client).

Зависимости: httpx (уже в requirements.txt).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PEOPLE_BASE = "https://people.googleapis.com/v1"
_PERSON_FIELDS = (
    "names,emailAddresses,phoneNumbers,organizations,"
    "birthdays,addresses,biographies,metadata"
)


# ---------------------------------------------------------------------------
# HTTP-слой (изолирован для мокирования)
# ---------------------------------------------------------------------------


async def _people_get_page(
    client: httpx.AsyncClient, url: str, headers: dict, params: dict
) -> dict:
    """Один GET к People API. Возвращает распарсенный JSON."""
    resp = await client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Маппинг Google → CRM
# ---------------------------------------------------------------------------


def map_google_to_crm(google_contact: dict) -> dict:
    """
    Преобразование одного контакта Google People → формат CRM.

    Возвращает dict, совместимый с ContactCreate.model_validate().
    """
    names = (google_contact.get("names") or [{}])[0]
    org = (google_contact.get("organizations") or [{}])[0]

    phones = [
        {"value": p.get("value", ""), "label": p.get("type", "другой") or "другой"}
        for p in google_contact.get("phoneNumbers") or []
        if p.get("value")
    ]

    emails = [
        {"value": e.get("value", ""), "label": e.get("type", "email") or "email"}
        for e in google_contact.get("emailAddresses") or []
        if e.get("value")
    ]

    birthday: Optional[str] = None
    bdays = google_contact.get("birthdays") or []
    if bdays:
        d = bdays[0].get("date") or {}
        if d.get("month") and d.get("day"):
            year = d.get("year") or 1900
            birthday = f"{year:04d}-{d['month']:02d}-{d['day']:02d}"

    city = ""
    addresses = google_contact.get("addresses") or []
    if addresses:
        city = addresses[0].get("city", "") or ""

    notes = ""
    bios = google_contact.get("biographies") or []
    if bios:
        notes = bios[0].get("value", "") or ""

    return {
        "first_name": names.get("givenName", "") or "",
        "last_name": names.get("familyName", "") or "",
        "phones": phones,
        "emails": emails,
        "company": org.get("name", "") or "",
        "position": org.get("title", "") or "",
        "city": city,
        "birthday": birthday,
        "notes": notes,
        "source": "google",
        "sources": ["google"],
        "external_ids": {
            "outlook": None,
            "google": google_contact.get("resourceName"),
            "telegram": None,
        },
        "category": "",
        "priority": "",
        "custom_fields": [],
        "relationships": [],
    }


def is_deleted(google_contact: dict) -> bool:
    """True если контакт помечен удалённым (приходит при sync через syncToken)."""
    meta = google_contact.get("metadata") or {}
    return bool(meta.get("deleted"))


# ---------------------------------------------------------------------------
# Полный pull
# ---------------------------------------------------------------------------


async def fetch_google_contacts(access_token: str) -> tuple[list[dict], str]:
    """
    Полная выгрузка контактов Google. Запрашивает syncToken для будущих
    инкрементальных синхронизаций.

    Возвращает (contacts, next_sync_token):
      contacts — список сырых People-документов (не замапленных)
      next_sync_token — сохранить в SyncConnection.contacts_sync_token
    """
    contacts: list[dict] = []
    url = f"{PEOPLE_BASE}/people/me/connections"
    headers = {"Authorization": f"Bearer {access_token}"}
    params: dict = {
        "personFields": _PERSON_FIELDS,
        "pageSize": "100",
        "requestSyncToken": "true",
    }
    next_sync_token = ""

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            data = await _people_get_page(client, url, headers, params)
            contacts.extend(data.get("connections") or [])
            next_sync_token = data.get("nextSyncToken") or next_sync_token
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            params["pageToken"] = page_token

    logger.info("fetch_google_contacts: получено %d контактов", len(contacts))
    return contacts, next_sync_token


# ---------------------------------------------------------------------------
# Инкрементальный sync (syncToken)
# ---------------------------------------------------------------------------


async def sync_google_contacts(
    access_token: str,
    sync_token: Optional[str] = None,
) -> tuple[list[dict], str]:
    """
    Инкрементальный sync через syncToken.

    Если sync_token не задан — делает полный pull (как fetch_google_contacts).
    Если Google вернёт 410 (syncToken протух) — поднимает httpx.HTTPStatusError,
    вызывающий код должен сделать полный resync.

    Возвращает (changed_contacts, next_sync_token). В changed_contacts могут
    быть удалённые (см. is_deleted).
    """
    if not sync_token:
        return await fetch_google_contacts(access_token)

    contacts: list[dict] = []
    url = f"{PEOPLE_BASE}/people/me/connections"
    headers = {"Authorization": f"Bearer {access_token}"}
    params: dict = {
        "personFields": _PERSON_FIELDS,
        "pageSize": "100",
        "syncToken": sync_token,
        "requestSyncToken": "true",
    }
    next_sync_token = ""

    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            data = await _people_get_page(client, url, headers, params)
            contacts.extend(data.get("connections") or [])
            next_sync_token = data.get("nextSyncToken") or next_sync_token
            page_token = data.get("nextPageToken")
            if not page_token:
                break
            params["pageToken"] = page_token

    logger.info("sync_google_contacts: %d изменений", len(contacts))
    return contacts, next_sync_token


# ---------------------------------------------------------------------------
# Push CRM → Google (двусторонний sync, Sprint 3)
# ---------------------------------------------------------------------------

_UPDATE_PERSON_FIELDS = "names,emailAddresses,phoneNumbers,organizations,biographies"


def map_crm_to_google(crm_contact: dict) -> dict:
    """Преобразование контакта CRM → формат People API для записи."""
    body: dict = {
        "names": [
            {
                "givenName": crm_contact.get("first_name", ""),
                "familyName": crm_contact.get("last_name", ""),
            }
        ],
        "emailAddresses": [
            {"value": e["value"]} for e in crm_contact.get("emails", []) if e.get("value")
        ],
        "phoneNumbers": [
            {"value": p["value"]} for p in crm_contact.get("phones", []) if p.get("value")
        ],
    }
    if crm_contact.get("company") or crm_contact.get("position"):
        body["organizations"] = [
            {"name": crm_contact.get("company", ""), "title": crm_contact.get("position", "")}
        ]
    if crm_contact.get("notes"):
        body["biographies"] = [{"value": crm_contact["notes"]}]
    return body


async def push_contact_to_google(access_token: str, crm_contact: dict) -> Optional[str]:
    """
    Создать или обновить контакт в Google.

    Если external_ids.google задан — updateContact (PATCH), иначе createContact (POST).
    Возвращает resourceName.
    """
    body = map_crm_to_google(crm_contact)
    resource = (crm_contact.get("external_ids") or {}).get("google")
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        if resource:
            # updateContact требует etag — получаем текущий контакт
            get_resp = await client.get(
                f"{PEOPLE_BASE}/{resource}",
                headers=headers,
                params={"personFields": "metadata"},
            )
            get_resp.raise_for_status()
            etag = get_resp.json().get("etag")
            body["etag"] = etag
            resp = await client.patch(
                f"{PEOPLE_BASE}/{resource}:updateContact",
                headers=headers,
                params={"updatePersonFields": _UPDATE_PERSON_FIELDS},
                json=body,
            )
            resp.raise_for_status()
            return resource
        resp = await client.post(
            f"{PEOPLE_BASE}/people:createContact", headers=headers, json=body
        )
        resp.raise_for_status()
        return resp.json().get("resourceName")
