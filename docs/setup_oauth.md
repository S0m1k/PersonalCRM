# Подключение Outlook и Google — регистрация приложения

Чтобы CRM могла читать и менять ваши контакты, её нужно один раз «зарегистрировать» в Microsoft и Google. Это бесплатно и занимает примерно 10 минут на каждого. На выходе получаются два значения — **ID клиента** и **секрет**, которые вписываются в `backend/.env`.

> Сейчас CRM работает на этом компьютере, поэтому адреса возврата — `http://localhost:8000/...`. При переезде на сервер (Sprint 8) добавим к ним адрес сервера.

---

## Microsoft (Outlook)

1. Откройте https://entra.microsoft.com и войдите **тем же аккаунтом, чей Outlook подключаем**.
2. **Applications → App registrations → New registration**:
   - **Name:** `PersonalCRM`
   - **Supported account types:** *Accounts in any organizational directory and personal Microsoft accounts*
   - **Redirect URI:** платформа **Web**, адрес `http://localhost:8000/api/sync/callback/microsoft`
   - **Register**
3. На странице приложения скопируйте **Application (client) ID** → это `MS_CLIENT_ID`.
4. **Certificates & secrets → Client secrets → New client secret**. Срок — 24 месяца. Скопируйте **Value** (не *Secret ID*!) сразу: позже его не показать → это `MS_CLIENT_SECRET`.
5. **API permissions → Add a permission → Microsoft Graph → Delegated permissions**, отметьте:
   - `Contacts.ReadWrite`
   - `User.Read`
   - `offline_access`

   **Add permissions.**

> ⚠️ **Если Outlook рабочий (корпоративный Microsoft 365)**, компания может запрещать сотрудникам самим давать доступ приложениям. Тогда при подключении появится «Требуется разрешение администратора» — нужно попросить IT-администратора нажать *Grant admin consent* для приложения `PersonalCRM`. С личными аккаунтами (outlook.com, hotmail) такого нет.

> 📅 Напоминание о сроке: секрет действует 24 месяца, потом его нужно перевыпустить (шаг 4) и заменить в `.env`.

---

## Google

1. Откройте https://console.cloud.google.com и войдите аккаунтом, чьи контакты подключаем.
2. Сверху **Select a project → New project**, имя `PersonalCRM` → **Create**, выберите его.
3. **APIs & Services → Library** → найдите **Google People API** → **Enable**.
4. **APIs & Services → OAuth consent screen** (может называться *Google Auth Platform*):
   - **User type:** *External*
   - **App name:** `PersonalCRM`, почта поддержки — ваша
   - **Scopes:** добавьте `.../auth/contacts`
   - **Test users:** добавьте свой Gmail
5. **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - **Application type:** *Web application*
   - **Authorized redirect URIs:** `http://localhost:8000/api/sync/callback/google`
   - **Create** → скопируйте **Client ID** → `GOOGLE_CLIENT_ID` и **Client secret** → `GOOGLE_CLIENT_SECRET`.

> ⚠️ **Важно про режим Testing.** Пока приложение в режиме *Testing*, Google выдаёт доступ к контактам **только на 7 дней** — потом придётся подключаться заново. Чтобы этого не было: **OAuth consent screen → Publishing status → Publish app**. Проверка Google для личного использования не нужна; при входе Google покажет предупреждение «Приложение не проверено» → *Дополнительно → Перейти на PersonalCRM*. Это нормально: приложение ваше.

---

## Вписать ключи и перезапустить

1. Откройте `backend/.env` и раскомментируйте/заполните:

   ```
   MS_CLIENT_ID=...
   MS_CLIENT_SECRET=...
   MS_TENANT=common
   MS_REDIRECT_URI=http://localhost:8000/api/sync/callback/microsoft

   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   GOOGLE_REDIRECT_URI=http://localhost:8000/api/sync/callback/google
   ```

2. Перезапустите backend, чтобы он прочитал новые настройки:

   ```bash
   docker compose up -d --force-recreate backend
   ```

3. Откройте http://localhost:3300/sync → **Подключить Outlook** / **Подключить Google** → войдите и разрешите доступ. Браузер вернётся в CRM, контакты подтянутся (первый раз — по кнопке синхронизации, дальше — сами каждые 5 минут).

## Если что-то пошло не так

| Что видно | Причина и решение |
|---|---|
| «OAuth ещё не настроен» | Ключи не вписаны в `backend/.env` или backend не перезапущен (шаг 2) |
| `AADSTS50011: redirect URI mismatch` | Адрес возврата в Entra не совпадает с `MS_REDIRECT_URI` — проверьте до символа |
| `redirect_uri_mismatch` (Google) | То же для Google: *Authorized redirect URIs* в Credentials |
| «Требуется разрешение администратора» | Корпоративный Microsoft 365 — нужен *Grant admin consent* от IT |
| `error=invalid_state` | Вход занял больше 15 минут или открыт из старой вкладки — нажмите «Подключить» ещё раз |
| Через неделю Google перестал синхронизироваться | Приложение в режиме *Testing* — опубликуйте (см. выше) и подключите заново |
