# PersonalCRM — Frontend

Next.js 14 (App Router, TypeScript).

## Локальный запуск

```bash
# 1. Установить зависимости
npm install

# 2. Скопировать конфиг
copy .env.local.example .env.local   # Windows
# cp .env.local.example .env.local   # Linux/macOS

# 3. Запустить dev-сервер
npm run dev
```

Фронтенд поднимется на http://localhost:3000.  
Главная страница отображает статус health-check бэкенда — убедитесь что бэкенд запущен.

## Структура

```
frontend/
├── app/
│   ├── layout.tsx   # корневой layout (html, body, метаданные)
│   └── page.tsx     # главная страница с health-check статусом
├── package.json
├── next.config.js
├── tsconfig.json
├── .env.local.example
└── README.md
```

## Переменные окружения

| Переменная              | По умолчанию              | Описание                     |
|-------------------------|---------------------------|------------------------------|
| `NEXT_PUBLIC_API_URL`   | `http://localhost:8000`   | URL FastAPI бэкенда          |

## Сборка для продакшна

```bash
npm run build
npm start
```

Для Docker-деплоя на Timeweb добавьте `output: 'standalone'` в `next.config.js` (Sprint 2+).
