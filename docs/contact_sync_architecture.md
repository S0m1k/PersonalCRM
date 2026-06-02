# Синхронизация контактов — архитектура

## Общая картина: откуда берутся контакты

```
┌──────────────────────────────────────────────────────────────┐
│                      Наше приложение (CRM)                    │
│                                                              │
│                    ┌──────────────────┐                       │
│                    │   Unified Contact │                       │
│                    │      Store        │                       │
│                    │    (MongoDB)      │                       │
│                    └────────▲─────────┘                       │
│                             │                                 │
│              ┌──────────────┼──────────────┐                  │
│              │              │              │                  │
│         ┌────┴────┐   ┌────┴────┐   ┌────┴────┐             │
│         │  Sync   │   │  Sync   │   │  Import │             │
│         │ Engine  │   │ Engine  │   │ Engine  │             │
│         │ MS Graph│   │ Google  │   │ Manual  │             │
│         └────┬────┘   └────┬────┘   └────┬────┘             │
└──────────────┼─────────────┼─────────────┼───────────────────┘
               │             │             │
               ▼             ▼             ▼
        ┌────────────┐ ┌──────────┐ ┌─────────────┐
        │  Microsoft │ │  Google  │ │   CSV/vCard  │
        │  Graph API │ │ People   │ │   Telegram   │
        │            │ │ API      │ │   export     │
        │ • Outlook  │ │ • Gmail  │ │              │
        │ • Exchange │ │ • Google │ │ • Телефонная │
        │ • Office365│ │   Contacts│ │   книга      │
        └────────────┘ └──────────┘ └─────────────┘
```

---

## Как Outlook связан с телефоном — и почему это важно

Outlook-контакты не живут в одном месте. Они реплицируются:

```
Microsoft 365 / Exchange Online
        │
        ├──→ Outlook Desktop (Windows/Mac)
        ├──→ Outlook Mobile (iOS/Android)
        ├──→ Outlook Web (outlook.office.com)
        │
        └──→ Телефонная книга
              (если включена синхронизация контактов)
              • iPhone: Настройки → Контакты → Аккаунты → Outlook
              • Android: Настройки → Аккаунты → Microsoft → Sync Contacts
```

То есть когда отец синхронизирует Outlook с телефоном — контакты в телефонной книге и в Outlook это одни и те же записи. Синхронизировать оба источника бессмысленно — получим дубликаты.

**Вывод для архитектуры:** если пользователь подключает Microsoft аккаунт, мы получаем и Outlook-контакты, и то, что у него на телефоне (через Outlook). Отдельный импорт из телефонной книги нужен только для контактов, которые НЕ из Outlook (например, сохранённые локально на телефоне или из Google).

---

## Источник 1: Microsoft Graph API (Outlook / Exchange / Office 365)

### Что даёт

Microsoft Graph — единая точка доступа к Outlook, Exchange, Office 365. Через одну авторизацию получаем:
- Контакты (все поля: имя, телефоны, email, компания, должность, день рождения, фото, заметки)
- Календарь (мы это уже описали)
- Почта (на будущее — вытаскивать контекст из переписки)

### Auth flow

```
Пользователь нажимает "Подключить Outlook"
        │
        ▼
  Redirect → Microsoft login
  (login.microsoftonline.com/common/oauth2/v2.0/authorize)
        │
        ▼
  Пользователь логинится, даёт разрешения:
  - Contacts.Read (чтение контактов)
  - Contacts.ReadWrite (если двусторонний sync)
  - Calendars.ReadWrite (календарь)
  - User.Read (профиль)
        │
        ▼
  Microsoft возвращает authorization code → наш backend
        │
        ▼
  Backend меняет code на access_token + refresh_token
  Сохраняем в MongoDB (зашифрованные)
```

### Синхронизация контактов

```python
# backend/sync/microsoft.py

import httpx

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

async def fetch_outlook_contacts(access_token: str) -> list[dict]:
    """Pull все контакты из Outlook через Microsoft Graph."""
    
    contacts = []
    url = f"{GRAPH_BASE}/me/contacts"
    params = {
        "$top": 100,  # пагинация
        "$select": "givenName,surname,emailAddresses,mobilePhone,"
                   "businessPhones,companyName,jobTitle,birthday,"
                   "personalNotes,homeAddress,businessAddress,"
                   "categories,photo"
    }
    
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        while url:
            resp = await client.get(url, headers=headers, params=params)
            data = resp.json()
            contacts.extend(data.get("value", []))
            url = data.get("@odata.nextLink")  # следующая страница
            params = {}  # nextLink уже содержит параметры
    
    return contacts


def map_outlook_to_crm(outlook_contact: dict) -> dict:
    """Преобразование формата Outlook → формат нашей CRM."""
    
    phones = []
    if outlook_contact.get("mobilePhone"):
        phones.append({
            "value": outlook_contact["mobilePhone"],
            "label": "мобильный"
        })
    for bp in outlook_contact.get("businessPhones", []):
        phones.append({"value": bp, "label": "рабочий"})
    
    emails = []
    for em in outlook_contact.get("emailAddresses", []):
        emails.append({
            "value": em.get("address", ""),
            "label": em.get("name", "email")
        })
    
    birthday = None
    if outlook_contact.get("birthday"):
        # Microsoft Graph возвращает "1985-03-15T00:00:00Z"
        birthday = outlook_contact["birthday"][:10]
    
    city = ""
    for addr_field in ["businessAddress", "homeAddress"]:
        addr = outlook_contact.get(addr_field, {})
        if addr and addr.get("city"):
            city = addr["city"]
            break
    
    return {
        "first_name": outlook_contact.get("givenName", ""),
        "last_name": outlook_contact.get("surname", ""),
        "phones": phones,
        "emails": emails,
        "company": outlook_contact.get("companyName", ""),
        "position": outlook_contact.get("jobTitle", ""),
        "city": city,
        "birthday": birthday,
        "notes": outlook_contact.get("personalNotes", ""),
        "source": "outlook",
        "external_ids": {
            "outlook": outlook_contact.get("id")
        },
        "category": "",        # пользователь заполнит
        "priority": "",        # пользователь заполнит
        "custom_fields": [],
        "relationships": []
    }
```

### Delta sync (инкрементальная синхронизация)

Полный pull каждый раз — дорого. Microsoft Graph поддерживает delta queries:

```python
async def delta_sync_contacts(access_token: str, delta_link: str = None):
    """Инкрементальный sync — только изменения с последнего раза."""
    
    if delta_link:
        # Используем сохранённый delta link
        url = delta_link
    else:
        # Первый sync — полный
        url = f"{GRAPH_BASE}/me/contacts/delta"
    
    changes = []
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async with httpx.AsyncClient() as client:
        while url:
            resp = await client.get(url, headers=headers)
            data = resp.json()
            
            for item in data.get("value", []):
                if "@removed" in item:
                    changes.append({"action": "deleted", "id": item["id"]})
                else:
                    changes.append({"action": "upsert", "data": item})
            
            # Следующая страница или delta link для следующего sync
            url = data.get("@odata.nextLink")
            if not url:
                next_delta = data.get("@odata.deltaLink")
    
    return changes, next_delta  # сохраняем next_delta в БД
```

### Webhooks (push-уведомления об изменениях)

Вместо polling — Microsoft присылает webhook когда контакт изменился:

```python
# Создание подписки на изменения контактов
async def subscribe_to_contact_changes(access_token: str, webhook_url: str):
    """Microsoft будет слать POST на webhook_url при любом изменении контактов."""
    
    subscription = {
        "changeType": "created,updated,deleted",
        "notificationUrl": webhook_url,  # https://app.domain.com/api/webhooks/microsoft
        "resource": "me/contacts",
        "expirationDateTime": "2026-06-09T00:00:00Z",  # максимум 3 дня, нужно продлевать
        "clientState": "crm-contact-sync"
    }
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GRAPH_BASE}/subscriptions",
            headers={"Authorization": f"Bearer {access_token}"},
            json=subscription
        )
        return resp.json()
```

### Двусторонний sync (наше приложение → Outlook)

Если пользователь создаёт или обновляет контакт в CRM — pushим в Outlook:

```python
async def push_contact_to_outlook(access_token: str, crm_contact: dict):
    """Создать или обновить контакт в Outlook."""
    
    outlook_format = {
        "givenName": crm_contact["first_name"],
        "surname": crm_contact["last_name"],
        "companyName": crm_contact.get("company", ""),
        "jobTitle": crm_contact.get("position", ""),
        "emailAddresses": [
            {"address": e["value"], "name": e.get("label", "")}
            for e in crm_contact.get("emails", [])
        ],
        "mobilePhone": next(
            (p["value"] for p in crm_contact.get("phones", [])
             if p.get("label") == "мобильный"),
            None
        ),
        "businessPhones": [
            p["value"] for p in crm_contact.get("phones", [])
            if p.get("label") == "рабочий"
        ],
        "personalNotes": crm_contact.get("notes", "")
    }
    
    outlook_id = crm_contact.get("external_ids", {}).get("outlook")
    
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {access_token}"}
        
        if outlook_id:
            # Update существующего
            await client.patch(
                f"{GRAPH_BASE}/me/contacts/{outlook_id}",
                headers=headers, json=outlook_format
            )
        else:
            # Create нового
            resp = await client.post(
                f"{GRAPH_BASE}/me/contacts",
                headers=headers, json=outlook_format
            )
            # Сохраняем outlook_id в нашей БД
            return resp.json().get("id")
```

---

## Источник 2: Google People API (Google Contacts / Gmail)

### Что даёт

Google People API — аналог Microsoft Graph для Google-экосистемы. Покрывает:
- Google Contacts
- Gmail-контакты (автосохранённые)
- Google Directory (для Workspace)

### Auth flow

Аналогичный OAuth 2.0:
- Scopes: `https://www.googleapis.com/auth/contacts` (read/write)
- Библиотека: `google-api-python-client`

### Ключевые отличия от Microsoft

| Аспект | Microsoft Graph | Google People API |
|--------|----------------|------------------|
| Delta sync | Встроенный (delta queries) | Через `syncToken` |
| Webhooks | Subscriptions API (макс 3 дня) | Нет для контактов (только polling) |
| Фото контакта | Через отдельный endpoint | Inline в response |
| Группы/категории | `categories` (массив строк) | `contactGroups` (отдельная сущность) |
| Rate limits | 10000 запросов / 10 минут | 90 запросов / минуту на пользователя |

### Sync flow

```python
# backend/sync/google.py

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

async def fetch_google_contacts(credentials: dict) -> list[dict]:
    """Pull контакты из Google."""
    
    creds = Credentials(
        token=credentials["access_token"],
        refresh_token=credentials["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET
    )
    
    service = build("people", "v1", credentials=creds)
    
    contacts = []
    page_token = None
    
    while True:
        results = service.people().connections().list(
            resourceName="people/me",
            pageSize=100,
            pageToken=page_token,
            personFields="names,emailAddresses,phoneNumbers,"
                        "organizations,birthdays,photos,"
                        "biographies,addresses,memberships"
        ).execute()
        
        contacts.extend(results.get("connections", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
    
    return contacts


def map_google_to_crm(google_contact: dict) -> dict:
    """Преобразование Google People → формат CRM."""
    
    name = google_contact.get("names", [{}])[0]
    org = google_contact.get("organizations", [{}])[0]
    birthday_data = google_contact.get("birthdays", [{}])[0].get("date", {})
    
    phones = [
        {"value": p.get("value", ""), "label": p.get("type", "другой")}
        for p in google_contact.get("phoneNumbers", [])
    ]
    
    emails = [
        {"value": e.get("value", ""), "label": e.get("type", "email")}
        for e in google_contact.get("emailAddresses", [])
    ]
    
    birthday = None
    if birthday_data.get("month") and birthday_data.get("day"):
        year = birthday_data.get("year", 1900)
        birthday = f"{year}-{birthday_data['month']:02d}-{birthday_data['day']:02d}"
    
    city = ""
    addresses = google_contact.get("addresses", [])
    if addresses:
        city = addresses[0].get("city", "")
    
    return {
        "first_name": name.get("givenName", ""),
        "last_name": name.get("familyName", ""),
        "phones": phones,
        "emails": emails,
        "company": org.get("name", ""),
        "position": org.get("title", ""),
        "city": city,
        "birthday": birthday,
        "notes": next(
            (b.get("value", "") for b in google_contact.get("biographies", [])),
            ""
        ),
        "source": "google",
        "external_ids": {
            "google": google_contact.get("resourceName")
        },
        "category": "",
        "priority": "",
        "custom_fields": [],
        "relationships": []
    }
```

---

## Источник 3: Ручной импорт (CSV, vCard, Telegram)

### Телефонная книга

С веба нет прямого доступа к контактам телефона. Варианты:

**Через подключённые аккаунты.** Если пользователь подключил Microsoft и/или Google — мы уже получили всё, что синхронизировано с телефоном. Большинство контактов на iPhone/Android привязаны к одному из этих аккаунтов.

**Экспорт вручную.** Пользователь экспортирует контакты с телефона:
- iPhone: iCloud → Экспорт vCard → загрузить в наше приложение
- Android: Google Contacts → Экспорт CSV → загрузить в наше приложение

### Telegram

Telegram позволяет экспортировать контакты:
- Telegram Desktop → Settings → Advanced → Export Telegram Data → Contacts (JSON)
- Формат: массив `{first_name, last_name, phone_number, date}`

### Парсеры

```python
# backend/import/parsers.py

import csv
import json
from io import StringIO


def parse_vcard(content: str) -> list[dict]:
    """Парсинг vCard (.vcf) формата."""
    contacts = []
    current = {}
    
    for line in content.splitlines():
        line = line.strip()
        if line == "BEGIN:VCARD":
            current = {}
        elif line == "END:VCARD":
            if current:
                contacts.append(current)
            current = {}
        elif ":" in line:
            key, _, value = line.partition(":")
            key_base = key.split(";")[0].upper()
            
            if key_base == "FN":
                parts = value.split(" ", 1)
                current["first_name"] = parts[0]
                current["last_name"] = parts[1] if len(parts) > 1 else ""
            elif key_base == "TEL":
                current.setdefault("phones", []).append({
                    "value": value, "label": "телефон"
                })
            elif key_base == "EMAIL":
                current.setdefault("emails", []).append({
                    "value": value, "label": "email"
                })
            elif key_base == "ORG":
                current["company"] = value.rstrip(";")
            elif key_base == "TITLE":
                current["position"] = value
            elif key_base == "BDAY":
                current["birthday"] = value  # формат: YYYYMMDD или YYYY-MM-DD
    
    return contacts


def parse_csv(content: str) -> list[dict]:
    """Парсинг CSV (Google Contacts export формат)."""
    reader = csv.DictReader(StringIO(content))
    contacts = []
    
    for row in reader:
        contact = {
            "first_name": row.get("First Name", row.get("Given Name", "")),
            "last_name": row.get("Last Name", row.get("Family Name", "")),
            "phones": [],
            "emails": [],
            "company": row.get("Company", row.get("Organization 1 - Name", "")),
            "position": row.get("Job Title", row.get("Organization 1 - Title", "")),
            "notes": row.get("Notes", ""),
        }
        
        # Телефоны (разные форматы CSV)
        for key in ["Phone 1 - Value", "Mobile Phone", "Primary Phone"]:
            if row.get(key):
                contact["phones"].append({"value": row[key], "label": "телефон"})
        
        # Email
        for key in ["E-mail 1 - Value", "E-mail Address", "Email"]:
            if row.get(key):
                contact["emails"].append({"value": row[key], "label": "email"})
        
        if contact["first_name"] or contact["last_name"]:
            contacts.append(contact)
    
    return contacts


def parse_telegram_export(content: str) -> list[dict]:
    """Парсинг Telegram contacts export (JSON)."""
    data = json.loads(content)
    
    # Telegram Desktop export формат
    contacts_list = data if isinstance(data, list) else data.get("contacts", {}).get("list", [])
    
    contacts = []
    for tc in contacts_list:
        contact = {
            "first_name": tc.get("first_name", ""),
            "last_name": tc.get("last_name", ""),
            "phones": [],
            "emails": [],
            "source": "telegram",
        }
        
        if tc.get("phone_number"):
            contact["phones"].append({
                "value": tc["phone_number"],
                "label": "telegram"
            })
        
        if contact["first_name"] or contact["last_name"]:
            contacts.append(contact)
    
    return contacts
```

### API для импорта

```
POST   /api/import/file                — загрузка файла (CSV, vCard, JSON)
POST   /api/import/preview             — превью: показать что будет импортировано, найти дубликаты
POST   /api/import/confirm             — подтвердить импорт (с выбором что импортировать)
```

---

## Дедупликация

Главная проблема: один человек может прийти из Outlook, Google и Telegram одновременно. Нужна стратегия merge.

### Алгоритм

```python
# backend/sync/dedup.py

from difflib import SequenceMatcher

def find_duplicates(new_contact: dict, existing_contacts: list[dict]) -> list[dict]:
    """Найти потенциальные дубликаты в существующей базе."""
    
    matches = []
    
    for existing in existing_contacts:
        score = 0
        reasons = []
        
        # 1. Точное совпадение телефона (самый надёжный сигнал)
        new_phones = {normalize_phone(p["value"]) for p in new_contact.get("phones", [])}
        existing_phones = {normalize_phone(p["value"]) for p in existing.get("phones", [])}
        if new_phones & existing_phones:
            score += 100
            reasons.append("совпадение телефона")
        
        # 2. Точное совпадение email
        new_emails = {e["value"].lower() for e in new_contact.get("emails", [])}
        existing_emails = {e["value"].lower() for e in existing.get("emails", [])}
        if new_emails & existing_emails:
            score += 90
            reasons.append("совпадение email")
        
        # 3. Fuzzy match по имени
        new_name = f"{new_contact.get('first_name', '')} {new_contact.get('last_name', '')}".strip().lower()
        existing_name = f"{existing.get('first_name', '')} {existing.get('last_name', '')}".strip().lower()
        
        if new_name and existing_name:
            name_ratio = SequenceMatcher(None, new_name, existing_name).ratio()
            if name_ratio > 0.85:
                score += 70
                reasons.append(f"похожее имя ({name_ratio:.0%})")
            elif name_ratio > 0.6:
                score += 30
                reasons.append(f"возможно похожее имя ({name_ratio:.0%})")
        
        # 4. Совпадение компании + похожее имя (усиливающий сигнал)
        if (new_contact.get("company", "").lower() == existing.get("company", "").lower()
                and new_contact.get("company")):
            score += 20
            reasons.append("та же компания")
        
        if score >= 70:
            matches.append({
                "existing_contact": existing,
                "score": min(score, 100),
                "reasons": reasons,
                "action": "auto_merge" if score >= 90 else "suggest_merge"
            })
    
    return sorted(matches, key=lambda x: x["score"], reverse=True)


def normalize_phone(phone: str) -> str:
    """Нормализация номера телефона для сравнения."""
    digits = "".join(c for c in phone if c.isdigit())
    # Российские номера: 8xxx → 7xxx
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def merge_contacts(primary: dict, secondary: dict) -> dict:
    """Слияние двух контактов. primary — основной, secondary — дополняющий."""
    
    merged = {**primary}
    
    # Телефоны: добавить уникальные из secondary
    existing_phones = {normalize_phone(p["value"]) for p in merged.get("phones", [])}
    for phone in secondary.get("phones", []):
        if normalize_phone(phone["value"]) not in existing_phones:
            merged.setdefault("phones", []).append(phone)
    
    # Email: добавить уникальные
    existing_emails = {e["value"].lower() for e in merged.get("emails", [])}
    for email in secondary.get("emails", []):
        if email["value"].lower() not in existing_emails:
            merged.setdefault("emails", []).append(email)
    
    # Заполнить пустые поля из secondary
    for field in ["company", "position", "city", "birthday", "notes"]:
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    
    # External IDs: объединить
    merged.setdefault("external_ids", {}).update(secondary.get("external_ids", {}))
    
    return merged
```

### UX дедупликации

При импорте/sync:

1. **Автоматический merge** (score ≥ 90): совпал телефон или email — объединяем без вопросов, обогащаем пустые поля
2. **Предложение merge** (score 70-89): "Этот контакт похож на существующий. Объединить?" — карточка с side-by-side сравнением
3. **Создание нового** (score < 70): создаём как отдельный контакт

---

## MongoDB: обновлённая модель контакта

```javascript
// Collection: contacts (обновлённая версия)
{
  _id: ObjectId,
  
  // ... все поля как раньше ...
  
  // Добавлено: внешние ID для sync
  external_ids: {
    outlook: String | null,     // Microsoft Graph contact ID
    google: String | null,      // Google People resourceName
    telegram: String | null     // (если будет API интеграция)
  },
  
  // Добавлено: источник и история sync
  source: String,               // "manual" | "outlook" | "google" | "csv" | "vcard" | "telegram"
  sources: [String],            // все источники (после merge может быть несколько)
  last_synced_at: Date | null,  // когда последний раз обновлён из внешнего источника
  sync_hash: String | null,     // хеш данных для определения изменений
  
  created_at: Date,
  updated_at: Date
}

// Collection: sync_connections (обновлённая, объединяет календарь и контакты)
{
  _id: ObjectId,
  provider: String,             // "microsoft" | "google" | "apple"
  
  // Auth
  access_token: String,         // зашифрованный
  refresh_token: String,        // зашифрованный
  token_expires_at: Date,
  
  // Что синхронизируем
  sync_contacts: Boolean,       // синкать контакты?
  sync_calendar: Boolean,       // синкать календарь?
  
  // Состояние sync
  contacts_delta_link: String | null,    // для Microsoft delta sync
  contacts_sync_token: String | null,    // для Google sync token
  contacts_last_sync: Date | null,
  calendar_last_sync: Date | null,
  
  // Webhooks
  webhook_subscription_id: String | null,
  webhook_expires_at: Date | null,
  
  created_at: Date,
  updated_at: Date
}

// Collection: sync_log (аудит)
{
  _id: ObjectId,
  connection_id: ObjectId,
  type: String,                 // "contacts" | "calendar"
  action: String,               // "full_sync" | "delta_sync" | "push" | "webhook"
  
  stats: {
    created: Number,
    updated: Number,
    deleted: Number,
    merged: Number,
    skipped: Number,
    errors: Number
  },
  
  errors: [{ contact_name: String, error: String }],
  
  started_at: Date,
  completed_at: Date
}
```

---

## API-эндпоинты (sync)

```
# Подключение провайдеров
GET    /api/sync/connections                  — список подключений
POST   /api/sync/connect/microsoft            — начать OAuth flow с Microsoft
POST   /api/sync/connect/google               — начать OAuth flow с Google
GET    /api/sync/callback/microsoft            — OAuth callback
GET    /api/sync/callback/google               — OAuth callback
DELETE /api/sync/connections/{id}              — отключить провайдер

# Синхронизация
POST   /api/sync/contacts/{connection_id}     — trigger sync контактов
GET    /api/sync/log                          — история sync
POST   /api/sync/contacts/{connection_id}/push/{contact_id}  — push контакта во внешний сервис

# Импорт файлов
POST   /api/import/upload                     — загрузить файл (CSV/vCard/JSON)
GET    /api/import/{import_id}/preview        — превью: что будет импортировано + дубликаты
POST   /api/import/{import_id}/confirm        — подтвердить импорт

# Webhooks (вызываются внешними сервисами)
POST   /api/webhooks/microsoft                — Microsoft push notification
POST   /api/webhooks/google                   — Google push notification (если включим)
```

---

## Sync Engine: фоновые задачи

```python
# backend/sync/engine.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# Периодический sync (fallback если webhooks не сработали)
@scheduler.scheduled_job("interval", minutes=30)
async def periodic_sync():
    """Фоновый sync каждые 30 минут для всех подключений."""
    connections = await db.sync_connections.find({"sync_contacts": True}).to_list()
    
    for conn in connections:
        try:
            if conn["provider"] == "microsoft":
                await delta_sync_microsoft_contacts(conn)
            elif conn["provider"] == "google":
                await incremental_sync_google_contacts(conn)
        except TokenExpiredError:
            await refresh_token(conn)
            # retry
        except Exception as e:
            await log_sync_error(conn["_id"], str(e))

# Обновление webhook подписок (Microsoft — каждые 2 дня)
@scheduler.scheduled_job("interval", hours=48)
async def renew_webhook_subscriptions():
    """Microsoft webhook подписки живут максимум 3 дня — продлеваем."""
    # ...

# Refresh OAuth tokens (проактивно, до истечения)
@scheduler.scheduled_job("interval", minutes=15)
async def refresh_expiring_tokens():
    """Обновить токены которые истекут в ближайшие 10 минут."""
    # ...
```

---

## Порядок реализации

### MVP (Спринт 2): минимальный sync

1. Microsoft Graph — OAuth + pull контактов + маппинг
2. Дедупликация — по телефону/email (автоматическая)
3. Импорт CSV/vCard — загрузка файла + превью + подтверждение
4. Одна кнопка "Синхронизировать" (ручной trigger)

### v2: полноценный sync

5. Google People API — OAuth + pull + маппинг
6. Delta sync (Microsoft) + sync tokens (Google)
7. Webhooks для real-time обновлений
8. Двусторонний push (наше приложение → Outlook/Google)
9. Разрешение конфликтов (last-write-wins или UI для выбора)
10. Telegram export import
11. Фоновый scheduler (APScheduler)

### v3: автоматизация

12. AI-assisted merge (нечёткий matching по имени + контексту)
13. Автоматическое обогащение (LinkedIn profile lookup — если разрешено)
14. Детекция "контакт сменил работу" (компания в Outlook изменилась)
