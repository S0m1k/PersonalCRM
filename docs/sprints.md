# План спринтов — PersonalCRM

> Черновик. Спринты ~2 недели. Приоритеты и объём уточняем перед стартом каждого.

## Обзор

| Спринт | Цель | Статус |
|--------|------|--------|
| Sprint 0 | Каркас проекта, инфраструктура | 🔜 |
| Sprint 1 | Ядро CRM: модель контакта, CRUD, базовый UI | ⬜ |
| Sprint 2 | MVP синхронизации (Microsoft Graph + импорт + дедуп) | ⬜ |
| Sprint 3 | Полноценный sync (Google, delta, webhooks, two-way) | ⬜ |
| Sprint 4 | Автоматизация и обогащение (AI-merge, scheduler) | ⬜ |

---

## Sprint 0 — Каркас и инфраструктура

**Цель:** репозиторий, окружение, скелет backend, БД поднимается локально.

- [x] Структура репозитория (`backend/`, `docs/`, `frontend/`)
- [x] FastAPI-скелет, health-check эндпоинт
- [x] Подключение к MongoDB (docker-compose для локалки)
- [x] Конфиг через `.env` (секреты, строки подключения)
- [ ] Базовый CI (линт + тесты)
- [ ] Шаблон для хранения зашифрованных токенов

**Definition of Done:** `docker-compose up` поднимает API + MongoDB, проходит health-check и линт.

---

## Sprint 1 — Ядро CRM

**Цель:** можно создавать/редактировать контакты вручную.

- [ ] Модель контакта (см. [архитектуру](contact_sync_architecture.md#mongodb-обновлённая-модель-контакта))
- [ ] CRUD-эндпоинты контактов (`/api/contacts`)
- [ ] Поля: имя, телефоны, emails, компания, должность, город, ДР, заметки, категория, приоритет, custom fields, relationships
- [ ] Поиск и фильтрация по контактам
- [ ] Простая авторизация (single-user: логин/пароль + сессия/JWT) — приложение на публичном хостинге
- [ ] Базовый UI на Next.js: список контактов + карточка (создание/редактирование)
- [ ] Тесты на модель и CRUD

**Definition of Done:** пользователь добавляет контакт вручную, видит в списке, редактирует, удаляет.

---

## Sprint 2 — MVP синхронизации

**Цель:** подтянуть контакты из Outlook и из файла, без дублей. (Раздел "MVP" в архитектуре.)

- [ ] OAuth-флоу с Microsoft (connect + callback, хранение токенов)
- [ ] Pull контактов через Microsoft Graph (`fetch_outlook_contacts`)
- [ ] Маппинг Outlook → модель CRM (`map_outlook_to_crm`)
- [ ] Дедупликация по телефону/email (автоматический merge ≥ 90)
- [ ] Импорт файла CSV/vCard: upload → preview (с дублями) → confirm
- [ ] Кнопка «Синхронизировать» (ручной trigger) + sync_log
- [ ] UI разрешения дублей (side-by-side для score 70–89)

**Definition of Done:** подключаю Outlook, жму «Синхронизировать» — контакты появляются без дублей; загружаю CSV — вижу превью и подтверждаю.

---

## Sprint 3 — Полноценный sync

**Цель:** real-time, двусторонний, Google. (Раздел "v2" в архитектуре.)

- [ ] Google People API: OAuth + pull + маппинг
- [ ] Delta sync (Microsoft) + sync tokens (Google)
- [ ] Webhooks Microsoft (subscription + продление каждые 48ч)
- [ ] Двусторонний push (CRM → Outlook/Google)
- [ ] Разрешение конфликтов (last-write-wins или UI выбора)
- [ ] Импорт Telegram export (JSON)
- [ ] Фоновый scheduler (APScheduler: periodic sync, refresh токенов)

**Definition of Done:** изменение в Outlook прилетает в CRM почти мгновенно; правка в CRM уходит обратно; Google подключается и синкается.

---

## Sprint 4 — Автоматизация и обогащение

**Цель:** умный merge и обогащение. (Раздел "v3" в архитектуре.)

- [ ] AI-assisted merge (нечёткий matching по имени + контексту)
- [ ] Автообогащение (LinkedIn lookup — если разрешено)
- [ ] Детекция «контакт сменил работу»
- [ ] Метрики качества дедупа

**Definition of Done:** TBD.

---

## Принятые решения

- **Бэкенд:** FastAPI + MongoDB (как в архитектуре)
- **Фронтенд:** Next.js (React) — с прицелом на масштабирование (SSR, роутинг, API routes)
- **Режим:** single-user (multi-user — на будущее, в модель данных не закладываем)
- **Хостинг:** Timeweb (нужен HTTPS-домен к Sprint 2 для OAuth redirect и webhooks)

## Открытые вопросы

- Хостинг и домен: какой провайдер? Нужен HTTPS-домен для OAuth callback Microsoft/Google и для webhooks.
- Apple/iCloud как источник — нужен ли? (пока считаем, что нет)
- Next.js: App Router или Pages Router? Что для запросов к API (React Query / SWR)?
- Next.js фронт и FastAPI бэк — деплоить на Timeweb раздельно или фронт через API routes как прокси?
