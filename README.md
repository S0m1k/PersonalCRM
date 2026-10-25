# PersonalCRM

Персональная CRM для управления контактами с синхронизацией из Outlook (Microsoft Graph), Google и ручным импортом (CSV / vCard / Telegram).

## Зачем

Контакты живут в разных местах — Outlook, телефонная книга, Google, Telegram. Эта CRM собирает их в единое хранилище, дедуплицирует и обогащает: категории, приоритеты, заметки, история взаимодействий.

## Стек (план)

- **Backend:** Python (FastAPI), MongoDB
- **Frontend:** Next.js (React)
- **Sync:** Microsoft Graph API, Google People API
- **Фоновые задачи:** APScheduler; Redis — счётчики рейт-лимитов
- **Режим:** несколько пользователей, открытая регистрация; у каждого своя база MongoDB (`personalcrm_u_<id>`)

## Документация

- [Архитектура синхронизации контактов](docs/contact_sync_architecture.md)
- [План спринтов](docs/sprints.md)

## Запуск (на этом компьютере)

Нужны **Docker Desktop** и **Python 3** (только для служебных скриптов).

```bash
python scripts/init_env.py       # один раз: создаёт backend/.env и backend/minio.env со случайными секретами
docker compose up -d --build     # вся система: MongoDB + Redis + MinIO + backend + frontend
```

Открыть: **http://localhost:3300** и зарегистрироваться (или войти как `admin` с паролем `ADMIN_PASSWORD` из `backend/.env` —
этот пользователь создаётся при первом запуске, ему же достаются данные однопользовательской версии).

Порты открыты только на этом компьютере (`127.0.0.1`):

| URL | Что |
|-----|-----|
| http://localhost:3300 | Интерфейс CRM |
| http://localhost:8000/api/health | Проверка API и базы |
| http://localhost:8000/docs | Swagger / OpenAPI |

### Подключить Outlook и Google

Пошагово: [docs/setup_oauth.md](docs/setup_oauth.md).

### Файлы к контактам

Вкладка «Файлы» в карточке контакта: загрузка (кнопкой или перетаскиванием), скачивание, удаление.
Файлы лежат в MinIO (S3-совместимое хранилище в том же docker compose, наружу не открыт), список — в базе пользователя.
Лимиты: 25 МБ на файл и 500 МБ на пользователя (`ATTACHMENT_MAX_MB`, `ATTACHMENTS_QUOTA_MB` в `backend/.env`).
Вместо MinIO подойдёт любой S3: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` в `backend/.env`.

Если `backend/.env` создан до появления вложений — снова запустите `python scripts/init_env.py`: он допишет только
недостающий `backend/minio.env`.

### Резервные копии

```bash
python scripts/backup.py                       # копия в ./backups, хранится 14 последних
python scripts/backup.py --dir D:/Backups/crm   # лучше — на другой диск или в облачную папку
python scripts/backup.py --restore backups/personalcrm-YYYYMMDD-HHMMSS.archive.gz
```

Рядом с дампом базы кладётся архив файлов-вложений `personalcrm-files-YYYYMMDD-HHMMSS.tar.gz`
(его снимает backend из S3/MinIO); `--restore` восстанавливает и его, если он лежит рядом.

### Разработка

```bash
cd backend && .venv/Scripts/python -m pytest -q     # тесты backend
docker compose stop frontend && cd frontend && npm run dev -- -p 3300   # фронтенд с горячей перезагрузкой вместо контейнера
```

---

## Статус

Sprint 4 — локальный запуск. См. [план спринтов](docs/sprints.md) и [концепцию](docs/vision/PersonalCRM_vision.pdf).
