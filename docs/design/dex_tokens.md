# Дизайн-система (по мотивам Dex)

Источник — CSS-переменные getdex.com (снято 2026-11-03). Берём структуру токенов, палитру нейтралей,
типографику, радиусы и тени. **Акцент — свой** (пресеты ниже), синий Dex не используем как основной.

## Шрифты

| Роль | Dex | У нас | Почему |
|------|-----|-------|--------|
| Текст UI | DM Sans 400/500/600/700 | **Onest** (запасной — Manrope) | у DM Sans нет кириллицы |
| Заголовки, имя контакта, «display» | Cormorant 500/600 | **Cormorant** (subsets: latin, cyrillic) | кириллица есть |

Через `next/font/google`, переменные `--font-sans` и `--font-display` (бывший `--font-serif`).
Имя контакта в карточке, заголовки страниц, «Welcome back»-подобные заголовки — Cormorant 600.
Подписи секций — UPPERCASE, 11px, letter-spacing .08em, цвет muted (как «DESCRIPTION», «ADDED» в Dex).

## Нейтрали (тёплые, светлая тема)

```
neutral-50  #faf9f7   фон страницы (background)
neutral-100 #f4f2ee   сайдбар, muted-поверхности
neutral-200 #e8e4de   границы, input
neutral-300 #d7d1c8   границы кнопок-outline
neutral-400 #b9b1a7   faint / иконки
neutral-500 #989082
neutral-600 #756d64   muted-foreground (вторичный текст)
neutral-700 #5a544d   foreground-secondary
neutral-900 #272421
neutral-950 #171513   основной текст
card        #ffffff
olive-100   #efebda   secondary (кнопки «второго плана»)
olive-200   #e0d8b8   secondary-hover
```

## Тёмная тема (slate)

```
slate-50 #f1f4f8 · slate-100 #e4e8ef · slate-300 #a8b3c7 · slate-400 #808da6 · slate-500 #5f6b84
slate-700 #364052 · slate-800 #262f40 · slate-900 #1a2130 · slate-950 #0f141d
background slate-950 · card slate-900 · border slate-700 · muted slate-800 · fg slate-50 · muted-fg slate-300
```

## Семантика

```
success  green-600 #2caf5e (dark: green-400 #7acd9a)
warning  gold-600  #faab29 (dark: gold-400  #fcca78)
danger   red-600   #d22839 (dark: red-400   #e37882)
```

CRM-цвета (как в Dex): relationship cold/warm/strong/vip = neutral-400 / gold-500 / green-600 / accent-600;
birthday = red-500; note = gold-600; email = accent-600; meeting = green-600; group = olive-600.

Палитра графиков: chart-1 accent-500, chart-2 green-600, chart-3 gold-600, chart-4 red-500, chart-5 olive-600.

## Акцент — пресеты (переключатель в «Аккаунт → Оформление»)

Шкала 50…950 у каждого пресета, хранится в `localStorage` и применяется классом на `<html>` (`accent-<name>`).

| Пресет | 500 (основной) | 600 (hover/текст) | 50 (подложка) |
|--------|----------------|-------------------|---------------|
| **Индиго** (по умолчанию) | #5b5bd6 | #4a48c4 | #f0f0fd |
| Терракота | #d0603a | #b44d2b | #fdf1ec |
| Изумруд | #1f9d6f | #17805a | #ebf8f2 |
| Слива | #9b4dca | #8239b0 | #f6eefc |
| Синий Dex | #4c79ff | #365eff | #eef3ff |

## Радиусы, тени, плотность

```
radius: sm .25rem · md .375rem · lg .5rem · xl .75rem · 2xl 1rem · 3xl 1.5rem
кнопки/инпуты — lg (8px); карточки-панели справа в Dex — 2xl (16px); пилюли (теги, «Set frequency») — full
elevation-xs 0 1px 2px 0 #1715130f
elevation-sm 0 2px 6px -1px #17151314
elevation-md 0 8px 20px -4px #1715131a
elevation-lg 0 18px 36px -10px #17151324
elevation-modal 0 24px 30px #17151324
```

Кнопки: primary — заливка accent-500, белый текст, hover accent-600, радиус lg, высота 32–36px.
Outline — белый фон, граница neutral-300, текст neutral-950, weight 500.
Пилюли-действия («Set priority», «Set frequency», «Add tags») — rounded-full, граница neutral-200, 12–13px, иконка 14px.
Аватар — круг с тёплой заливкой (по хешу имени из тёплой палитры) и буквой.

## Отклонения реализации (W0-A)

- **Контраст кнопок.** Белый текст на 500-м шаге не проходит 4.5:1 у Терракоты (3.9), Изумруда (3.4) и Синего Dex (3.8).
  Поэтому токен `accent` (заливка кнопок, ссылки, фокус) в светлой теме = шаг **600** (белый текст 4.9–7.0), hover = 700;
  шаг 500 остаётся в шкале (`accent-500`, графики, образцы цвета). В тёмной теме `accent` = шаг 400, `accent-fg` = тёмный slate (5.3–7.3).
- Шкалы 100–400 и 700–950 сгенерированы смешением заданных 50/500/600; спецификация даёт только 50/500/600.
- `faint` = neutral-500 (#989082), а не 400: токен используется и для текста (счётчики, подсказки).
- `olive-600` (#7e7542) и gold-500 для `crm-warm` подобраны вручную — в снятых переменных их значений не было.
- Тема: светлая / тёмная / «как в системе» (по умолчанию). Акцент: `localStorage['crm_accent']`, класс `accent-<id>` на `<html>`.

## Реализация

- `frontend/app/globals.css` — переменные в формате RGB-троек (как сейчас), имена токенов Tailwind
  (`bg`, `sidebar`, `surface`, `fg`, `muted`, `faint`, `line`, `hover`, `accent`, `accent-fg`, `danger`) сохраняем,
  чтобы существующие страницы перекрасились без правок; добавляем `accent-50…950`, `success`, `warning`,
  `olive`, `chart-1…5`, `crm-*`, `shadow-xs…modal`, `font-display`.
- Общие компоненты: `Card` (rounded-2xl, border line, bg surface), `SectionLabel` (uppercase), `Pill`,
  `Button` (primary / outline / ghost / secondary).
