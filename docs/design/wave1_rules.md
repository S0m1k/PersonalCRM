# Правила для агентов волны 1

## Старт
1. `git merge refs/heads/claude/getdex-structure-redesign-ba1128` (в нём дизайн-система, модель данных, ИИ 2.0).
2. Прочитать: `docs/dex_redesign_plan.md`, `docs/design/dex_tokens.md`, `docs/design/dex_screens.md` (структура экранов Dex — главный ориентир),
   `docs/data_model_sprint11.md` (новые поля и API).
3. Python: `C:/Users/somov/PersonalCRM/backend/.venv/Scripts/python -m pytest -q` из `backend/`. Фронт: `npm ci` в `frontend/`, если нет `node_modules`.

## Что уже есть — использовать, не дублировать
- UI: `components/ui/card.tsx` (`Card`, `CardHeader label action`, `CardAction`), `section-label.tsx`, `pill.tsx` (`Pill icon isActive`),
  `button.tsx` (variants `primary|outline|secondary|ghost|danger`, sizes `sm|md|icon`), `tag.tsx`, `input.tsx`,
  `overlays.tsx` (Dialog, Menu, Popover, Tabs с подчёркиванием), `components/app/avatar.tsx`, `page.tsx` (`Page`, `PageHeader`, `EmptyState`, `SectionTitle`, `Skeleton`).
- Токены Tailwind: `bg/surface/sidebar/fg/muted/faint/line/line-strong/hover`, `accent`, `accent-50…950`, `accent-fg`, `accent-hover`, `success`, `warning`, `danger`,
  `olive-100/200/600`, `chart-1…5`, `crm-cold|warm|strong|vip|birthday|note|email|meeting|group`, тени `shadow-xs…modal`, `font-display` (Cormorant).
  **Никаких hex-цветов в компонентах.** Для canvas/SVG брать цвета через `getComputedStyle(document.documentElement).getPropertyValue('--chart-1')` (RGB-тройки → `rgb(...)`).
- Данные: `lib/api.ts` (`Contact`, `apiFetch`, `fetcher`, ключи SWR), `lib/api-crm.ts` (группы, теги, взаимодействия, keep-in-touch, сеть),
  `lib/api-assistant.ts` (чаты, досье), `lib/priority.ts` (уровни `top|high|medium|low|none`, подписи), `lib/frequency.ts` (пресеты частоты).
- Сайдбар уже содержит все разделы и подразделы (`/reminders`, `/contacts/birthdays|quick-action|merge|locations`, `/network/insights`). **Не правьте `sidebar.tsx`**,
  кроме агента «Контакты», которому принадлежит `components/app/sidebar-views.tsx`.

## Границы
- Каждый агент правит только свои маршруты/компоненты. Общие файлы (`lib/api.ts`, `main.py`, `models/contact.py`) — минимальные точечные добавления.
- Новый API-клиент — в своём `lib/api-<фича>.ts`; новый роутер — свой файл в `backend/app/routers/` + одна строка `include_router` в `main.py`.
- Тексты UI — по-русски. Названия разделов «Keep in Touch», «Timeline», «Priority Map» оставляем как в сайдбаре.

## Качество
- TDD для backend-логики, `pytest -q` зелёный.
- `npm run lint` (0 ошибок) и `npm run build` зелёные.
- Доступность: клавиатура, `aria-label` у иконок-кнопок, у drag-and-drop есть альтернатива без мыши (меню/кнопки).
- Пустые состояния и скелетоны загрузки на каждом экране.
- Conventional commits, в конце каждого `Co-Authored-By: Claude Sonnet <noreply@anthropic.com>`. Не пушить.
- В отчёте: ветка, коммиты, что сделано, что не проверено, известные проблемы.
