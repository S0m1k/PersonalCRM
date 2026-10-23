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

## Запуск (на этом компьютере)

Нужны **Docker Desktop** и **Python 3** (только для служебных скриптов).

```bash
python scripts/init_env.py       # один раз: создаёт backend/.env со случайными секретами
docker compose up -d --build     # вся система: MongoDB + backend + frontend
```

Открыть: **http://localhost:3300** — пользователь `admin`, пароль — строка `ADMIN_PASSWORD` в `backend/.env`.

Порты открыты только на этом компьютере (`127.0.0.1`):

| URL | Что |
|-----|-----|
| http://localhost:3300 | Интерфейс CRM |
| http://localhost:8000/api/health | Проверка API и базы |
| http://localhost:8000/docs | Swagger / OpenAPI |

### Подключить Outlook и Google

Пошагово: [docs/setup_oauth.md](docs/setup_oauth.md).

### Резервные копии

```bash
python scripts/backup.py                       # копия в ./backups, хранится 14 последних
python scripts/backup.py --dir D:/Backups/crm   # лучше — на другой диск или в облачную папку
python scripts/backup.py --restore backups/personalcrm-YYYYMMDD-HHMMSS.archive.gz
```

### Разработка

```bash
cd backend && .venv/Scripts/python -m pytest -q     # тесты backend
docker compose stop frontend && cd frontend && npm run dev -- -p 3300   # фронтенд с горячей перезагрузкой вместо контейнера
```

---

## Статус

Sprint 4 — локальный запуск. См. [план спринтов](docs/sprints.md) и [концепцию](docs/vision/PersonalCRM_vision.pdf).
