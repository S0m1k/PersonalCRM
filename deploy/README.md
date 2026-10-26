# Запуск на сервере

Схема: телефон / браузер → **Tailscale Funnel** (HTTPS) → **Caddy** `:8081` → `/api`, `/dav` — backend, остальное — frontend.
В домашней сети тот же Caddy доступен напрямую: `http://<IP-сервера>:8081`.

## Первый запуск

```bash
python3 scripts/init_env.py                      # backend/.env и backend/minio.env со случайными секретами
```

Уже работающий сервер без вложений: тот же `init_env.py` создаст только недостающий `backend/minio.env`
(без него `docker compose` не запустится). Пароль MinIO после первого запуска не менять — он записан в его данных.

В `backend/.env` поправить (`TRUST_PROXY_HEADERS=true` задаёт `deploy/docker-compose.server.yml`):

```
FRONTEND_URL=https://<имя>.<tailnet>.ts.net
PUBLIC_BASE_URL=https://<имя>.<tailnet>.ts.net
```

```bash
docker compose -p personalcrm -f docker-compose.yml -f deploy/docker-compose.server.yml up -d --build
```

## Tailscale Funnel

1. В https://login.tailscale.com/admin/settings/keys — **Generate auth key** (одноразовый, срок — день).
2. Войти ключом (ключ — из файла, чтобы не светить его в истории команд):

   ```bash
   T="docker exec personalcrm-tailscale-1 tailscale --socket=/tmp/tailscaled.sock"
   $T up --hostname=personalcrm --authkey="$(cat ts.key)" && rm ts.key
   $T funnel --bg 8081
   ```

   При первом `funnel` Tailscale даст ссылку, чтобы разрешить Funnel в сети, — открыть, разрешить и повторить команду.
   Если после разрешения пишет «port 443 is not allowed» — перезапустить контейнер `tailscale`, он подтянет права.
3. Сертификат выпускается при первых запросах, иногда до получаса: до этого браузер обрывает соединение на TLS.
   Готовность — файл `.crt` в `docker exec personalcrm-tailscale-1 ls /var/lib/tailscale/certs`.

Вход и настройки Funnel хранятся в томе `tailscale_state` и переживают перезапуски.

## Модель ИИ (Ollama на контейнере 102, ai-lxc)

Модель держится в видеопамяти постоянно, иначе Ollama выгружает её после простоя и первый
запрос ждёт ~40 с загрузки. На контейнере:

- `/etc/systemd/system/ollama.service.d/zz-crm-keepalive.conf` — `OLLAMA_KEEP_ALIVE=-1`
  и предзагрузка модели при старте сервиса (`ExecStartPost`, в фоне);
- `/usr/local/bin/crm-ollama-preload.sh` — сама предзагрузка (модель — `CRM_PRELOAD_MODEL`,
  по умолчанию `qwen3.5:4b`; при смене `LLM_MODEL` поменять и здесь).

Проверка: `ollama ps` — в колонке UNTIL `Forever`. Откат: удалить оба файла,
`systemctl daemon-reload && systemctl restart ollama`.

## Резервные копии

```bash
python3 scripts/backup.py --dir /mnt/backup/crm   # лучше на другой диск или машину
```

В копию входят базы MongoDB и файлы-вложения из MinIO (том `minio_data`), см. `scripts/backup.py`.
Файлы отдаются через backend (MinIO наружу не открыт); тело запроса на загрузку — до 25 МБ (+ запас на multipart).
