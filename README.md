# PersonalCRM

Персональная CRM для управления контактами с синхронизацией из Outlook (Microsoft Graph), Google и ручным импортом (CSV / vCard / Telegram).

## Зачем

Контакты живут в разных местах — Outlook, телефонная книга, Google, Telegram. Эта CRM собирает их в единое хранилище, дедуплицирует и обогащает: категории, приоритеты, заметки, история взаимодействий.

## Стек (план)

- **Backend:** Python (FastAPI), MongoDB
- **Frontend:** Next.js (React)
- **Sync:** Microsoft Graph API, Google People API
- **Фоновые задачи:** APScheduler
- **Режим:** single-user (multi-user — на будущее)

## Документация

- [Архитектура синхронизации контактов](docs/contact_sync_architecture.md)
- [План спринтов](docs/sprints.md)

## Запуск (локально)

### 1. MongoDB + Backend (через Docker Compose)

```bash
docker-compose up --build
```

Поднимает:
- **MongoDB 7** на порту `27017` (данные в Docker volume `mongo_data`)
- **FastAPI backend** на порту `8000` (собирается из `./backend`)

Health-check: http://localhost:8000/api/health  
Swagger UI: http://localhost:8000/docs

### 2. Frontend (Next.js)

```bash
cd frontend
npm install
cp .env.local.example .env.local   # или copy на Windows
npm run dev
```

Фронтенд поднимается на http://localhost:3000 и отображает статус бэкенда.

### Проверка после запуска

| URL | Что проверяем |
|-----|---------------|
| http://localhost:8000/api/health | API + MongoDB ping |
| http://localhost:8000/docs | Swagger / OpenAPI |
| http://localhost:3000 | UI со статусом сервисов |

---

## Статус

Sprint 0 — скелет проекта. См. [план спринтов](docs/sprints.md).
