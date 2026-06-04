"""
Движок синхронизации Microsoft Graph контактов.

Основные функции:
  - fetch_outlook_contacts  — полный pull (без delta-link)
  - delta_sync_contacts     — инкрементальный pull через Microsoft Graph delta queries
  - map_outlook_to_crm      — маппинг формата Graph → модель CRM

Все HTTP-вызовы изолированы в отдельные функции (_graph_get_page)
для простого мокирования в тестах.

Зависимости: httpx (уже в requirements.txt).
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Поля контакта, которые запрашиваем из Graph API
_CONTACT_SELECT = (
    "id,givenName,surname,emailAddresses,mobilePhone,"
    "businessPhones,companyName,jobTitle,birthday,"
    "personalNotes,homeAddress,businessAddress,categories"
)


# ---------------------------------------------------------------------------
# HTTP-слой (изолирован для мокирования)
# ---------------------------------------------------------------------------


async def _graph_get_page(client: httpx.AsyncClient, url: str, headers: dict, params: dict = None) -> dict:
    """Один GET-запрос к Graph API. Возвращает распарсенный JSON."""
    resp = await client.get(url, headers=headers, params=params or {})
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Маппинг Outlook → CRM
# ---------------------------------------------------------------------------


def map_outlook_to_crm(outlook_contact: dict) -> dict:
    """
    Преобразование одного контакта из формата Microsoft Graph → формат CRM.

    Входной dict — значение из поля "value" ответа Graph API.
    Возвращает dict, совместимый с ContactCreate.model_validate().
    """
    phones: list[dict] = []
    if outlook_contact.get("mobilePhone"):
        phones.append({"value": outlook_contact["mobilePhone"], "label": "мобильный"})
    for bp in outlook_contact.get("businessPhones") or []:
        phones.append({"value": bp, "label": "рабочий"})

    emails: list[dict] = []
    for em in outlook_contact.get("emailAddresses") or []:
        address = em.get("address", "").strip()
        if address:
            emails.append({"value": address, "label": em.get("name", "email") or "email"})

    # birthday: Graph возвращает "1985-03-15T00:00:00Z"
    birthday: Optional[str] = None
    raw_bday = outlook_contact.get("birthday")
    if raw_bday and isinstance(raw_bday, str) and len(raw_bday) >= 10:
        birthday = raw_bday[:10]

    # Город: ищем в businessAddress, затем homeAddress
    city = ""
    for addr_field in ("businessAddress", "homeAddress"):
        addr = outlook_contact.get(addr_field) or {}
        if isinstance(addr, dict) and addr.get("city"):
            city = addr["city"]
            break

    return {
        "first_name": outlook_contact.get("givenName") or "",
        "last_name": outlook_contact.get("surname") or "",
        "phones": phones,
        "emails": emails,
        "company": outlook_contact.get("companyName") or "",
        "position": outlook_contact.get("jobTitle") or "",
        "city": city,
        "birthday": birthday,
        "notes": outlook_contact.get("personalNotes") or "",
        "source": "outlook",
        "sources": ["outlook"],
        "external_ids": {
            "outlook": outlook_contact.get("id"),
            "google": None,
            "telegram": None,
        },
        "category": "",
        "priority": "",
        "custom_fields": [],
        "relationships": [],
    }


# ---------------------------------------------------------------------------
# Полный pull
# ---------------------------------------------------------------------------


async def fetch_outlook_contacts(access_token: str) -> list[dict]:
    """
    Полная выгрузка всех контактов из Outlook через Microsoft Graph.

    Обрабатывает пагинацию (@odata.nextLink).
    Возвращает список сырых Graph-документов (не замапленных).
    """
    contacts: list[dict] = []
    url = f"{GRAPH_BASE}/me/contacts"
    params: dict = {"$top": "100", "$select": _CONTACT_SELECT}
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            data = await _graph_get_page(client, url, headers, params)
            contacts.extend(data.get("value") or [])
            url = data.get("@odata.nextLink")   # type: ignore[assignment]
            params = {}  # nextLink уже содержит параметры

    logger.info("fetch_outlook_contacts: получено %d контактов", len(contacts))
    return contacts


# ---------------------------------------------------------------------------
# Инкрементальный sync (delta)
# ---------------------------------------------------------------------------


async def delta_sync_contacts(
    access_token: str,
    delta_link: Optional[str] = None,
) -> tuple[list[dict], str]:
    """
    Инкрементальный sync — только изменения с последнего раза.

    Если delta_link задан — использует его (следующий incremental sync).
    Иначе — первый полный sync через /me/contacts/delta.

    Возвращает (changes, next_delta_link):
      changes: list[dict] с полями "action" ("upsert" | "deleted") и "data" / "id"
      next_delta_link: сохранить в SyncConnection.contacts_delta_link
    """
    changes: list[dict] = []
    next_delta: str = ""

    if delta_link:
        url: Optional[str] = delta_link
        params: dict = {}
    else:
        url = f"{GRAPH_BASE}/me/contacts/delta"
        params = {"$select": _CONTACT_SELECT}

    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        while url:
            data = await _graph_get_page(client, url, headers, params)
            params = {}

            for item in data.get("value") or []:
                if "@removed" in item:
                    changes.append({"action": "deleted", "id": item.get("id")})
                else:
                    changes.append({"action": "upsert", "data": item})

            next_link = data.get("@odata.nextLink")
            delta_link_new = data.get("@odata.deltaLink")

            if next_link:
                url = next_link
            else:
                if delta_link_new:
                    next_delta = delta_link_new
                url = None  # завершаем цикл

    logger.info(
        "delta_sync_contacts: %d изменений, следующий delta_link %s",
        len(changes),
        "получен" if next_delta else "отсутствует",
    )
    return changes, next_delta
