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

## Статус

🚧 Планирование. См. [план спринтов](docs/sprints.md).
