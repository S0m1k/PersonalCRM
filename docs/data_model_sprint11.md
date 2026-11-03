# Модель данных Sprint 11

Данные для экранов в стиле Dex (см. [dex_redesign_plan.md](dex_redesign_plan.md)). Все коллекции — в базе
пользователя, все запросы идут через `get_user_db`. Фронт: типы в `frontend/lib/api.ts`, клиент в `frontend/lib/api-crm.ts`.

## Поля контакта (все необязательные, старые документы читаются)

| Поле | Тип | Правила |
|------|-----|---------|
| `description` | str ≤2000 | короткое био, отдельно от `notes` |
| `tags` | list[str] | trim, без дублей (без учёта регистра), ≤50 символов, ≤50 тегов |
| `group_ids` | list[str] | id существующих групп, иначе 422 |
| `keep_in_touch` | `{frequency_days 1..730 \| null, snoozed_until YYYY-MM-DD \| null}` | |
| `first_met_at` / `first_met_note` | YYYY-MM-DD \| null / str | |
| `last_interaction_at` | datetime \| null | **только чтение**: максимум из взаимодействий и прошедших событий календаря |
| `address` | str | |
| `location` | `{lat -90..90, lng -180..180, label}` \| null | |
| `social` | `{linkedin, facebook, instagram, telegram, twitter, website}` | http(s)-ссылка или ник; `javascript:` и пр. → 422 |
| `importance`, `closeness` | 1..5 \| null | оси Priority Map |
| `life_areas` | list[str] | как теги; сферы «Колеса баланса» |

Даты хранятся строками `YYYY-MM-DD` (как `birthday`). В PATCH явный `null` очищает только `first_met_at`,
`location`, `importance`, `closeness`; у остальных полей `null` значит «не менять».

## Коллекции

- `groups`: `{name, emoji, color, description, created_at}`; имя уникально без учёта регистра (409).
- `interactions`: `{contact_ids[], kind: note|call|meeting|message|email|other, title, body, occurred_at, source: manual|calendar|ai|import, created_at, updated_at}`.
  Индексы: `(contact_ids, occurred_at desc)`, `(occurred_at desc)`. Удаление контакта убирает его id; опустевшие записи удаляются.
- Прошедшие события календаря не копируются: при `include_events=true` они подмешиваются как `meeting` с `source: calendar`,
  `read_only: true`, `id: "event:<id>"`.

## last_interaction_at

Пересчитывается при создании / изменении / удалении взаимодействия и события (через `/api/calendar/events`).
События, пришедшие синхронизацией с провайдером, поле не обновляют; `GET /api/keep-in-touch` и сводка главной
считают «свежее» значение на лету, поэтому в них это не мешает. Будущие записи не учитываются.
`updated_at` контакта при этом не меняется (синхронизацию с провайдерами это не запускает).

## Эндпоинты

| Метод и путь | Назначение |
|--------------|-----------|
| `GET/POST /api/groups`, `PATCH/DELETE /api/groups/{id}` | группы; в списке `member_count` |
| `GET /api/tags`, `POST /api/tags/rename {from,to}`, `DELETE /api/tags/{tag}` | теги со счётчиками, переименование/слияние, удаление у всех |
| `GET/POST /api/interactions`, `PATCH/DELETE /api/interactions/{id}` | лента, фильтры `contact_id kind from to q include_events`, курсор `cursor` + `limit` (1..200) |
| `GET /api/keep-in-touch?today=` | `{overdue, due_soon, upcoming, snoozed}` |
| `POST /api/contacts/{id}/snooze {days 1..365, today?}` | отложить напоминание |
| `POST /api/contacts/{id}/touched {kind?, title?, body?}` | быстрое взаимодействие «Связались», снимает отсрочку |
| `GET /api/contacts?tag&group_id&has_location&sort=last_interaction\|name\|created\|importance` | фильтры списка |
| `GET /api/network?min_weight=` | граф: узлы (≤500, самые важные) и рёбра `relationship` / `together` |
| `GET /api/home` | + `keep_in_touch_overdue` (5), `recent_interactions` (5), `counts {groups, tags}` |

Keep in touch: срок = последнее взаимодействие (нет — дата создания) + частота; «скоро» — срок сегодня или в
ближайшие 7 дней; отложенные (до даты включительно) всегда в `snoozed`.
