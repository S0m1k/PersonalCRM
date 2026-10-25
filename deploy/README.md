# Запуск на сервере

Схема: телефон / браузер → **Tailscale Funnel** (HTTPS) → **Caddy** `:8081` → `/api`, `/dav` — backend, остальное — frontend.
В домашней сети тот же Caddy доступен напрямую: `http://<IP-сервера>:8081`.

## Первый запуск

```bash
python3 scripts/init_env.py                      # backend/.env со случайными секретами
```

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

## Резервные копии

```bash
python3 scripts/backup.py --dir /mnt/backup/crm   # лучше на другой диск или машину
```
