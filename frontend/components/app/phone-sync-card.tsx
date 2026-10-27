'use client';

/**
 * Карточка «Телефон»: как подключить контакты и календарь iPhone / Android по CardDAV и CalDAV.
 * Пароль для телефона выпускает сам пользователь; он показывается один раз,
 * на сервере хранится только отпечаток.
 */

import { useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { Apple, Check, Copy, KeyRound, Smartphone } from 'lucide-react';
import {
  API_URL,
  issueCarddavPassword,
  meKey,
  revokeCarddavPassword,
  type CarddavPassword,
  type CarddavStatus,
} from '@/lib/api';
import { cn, errorText } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Tag } from '@/components/ui/tag';

const STATUS_KEY = '/api/carddav/status';

type Platform = 'ios' | 'android';

type Server = { host: string; origin: string; isHttps: boolean };

/** Адрес, по которому телефон достучится до backend (CardDAV живёт там же, где API). */
function davServer(): Server | null {
  if (typeof window === 'undefined') return null;
  const url = new URL(API_URL || window.location.origin);
  const isLocal = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
  const host = isLocal ? `IP-этого-ПК${url.port ? `:${url.port}` : ''}` : url.host;
  return { host, origin: `${url.protocol}//${host}`, isHttps: url.protocol === 'https:' };
}

export function PhoneSyncCard() {
  const { data: status } = useSWR<CarddavStatus>(STATUS_KEY);
  const { mutate } = useSWRConfig();
  const [platform, setPlatform] = useState<Platform>('ios');
  const [issued, setIssued] = useState<CarddavPassword | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const server = davServer();

  async function refresh() {
    await Promise.all([mutate(STATUS_KEY), mutate(meKey)]);
  }

  async function handleIssue() {
    if (status?.enabled && !window.confirm('Старый пароль перестанет работать — телефон придётся перенастроить. Продолжить?')) {
      return;
    }
    setIsBusy(true);
    try {
      setIssued(await issueCarddavPassword());
      await refresh();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsBusy(false);
    }
  }

  async function handleRevoke() {
    if (!window.confirm('Отключить телефон? Контакты и календарь CRM пропадут с телефона.')) return;
    setIsBusy(true);
    try {
      await revokeCarddavPassword();
      setIssued(null);
      await refresh();
      toast.success('Телефон отключён');
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <div className="mb-10 rounded-lg border border-line p-4">
      <div className="mb-2 flex items-center gap-2.5">
        <Smartphone className="size-6 text-muted" strokeWidth={1.6} />
        <span className="font-semibold">Телефон</span>
        {status && <Tag color={status.enabled ? 'green' : 'gray'}>{status.enabled ? 'включено' : 'выключено'}</Tag>}
      </div>
      <p className="mb-4 text-sm text-muted">
        Контакты CRM появятся в обычной «Звонилке» отдельной адресной книгой, а встречи — в «Календаре» отдельным
        календарём. Правки на телефоне попадают в CRM и обратно. Удалённые на телефоне контакты и события уходят в корзину,
        а не пропадают насовсем. События из Outlook и Google на телефоне только читаются — правьте их в CRM.
      </p>

      {status && server && (
        <dl className="mb-4 grid grid-cols-[110px_1fr] items-center gap-x-3 gap-y-1.5 text-sm">
          <dt className="text-muted">Сервер</dt>
          <dd><CopyValue value={server.host} /></dd>
          <dt className="text-muted">Пользователь</dt>
          <dd><CopyValue value={status.username} /></dd>
          <dt className="text-muted">Пароль</dt>
          <dd>
            {issued ? (
              <span className="inline-flex flex-wrap items-center gap-2">
                <CopyValue value={issued.password} />
                <span className="text-xs text-danger">виден только сейчас — сохраните или сразу введите в телефоне</span>
              </span>
            ) : (
              <span className="text-muted">{status.enabled ? 'выпущен ранее (не показывается)' : 'ещё не выпущен'}</span>
            )}
          </dd>
        </dl>
      )}

      <div className="mb-5 flex flex-wrap gap-1.5">
        <Button size="sm" variant={status?.enabled ? 'outline' : 'primary'} onClick={handleIssue} disabled={isBusy || !status}>
          <KeyRound />
          {status?.enabled ? 'Выпустить новый пароль' : 'Выпустить пароль для телефона'}
        </Button>
        {status?.enabled && (
          <Button size="sm" variant="danger" onClick={handleRevoke} disabled={isBusy}>
            Отключить телефон
          </Button>
        )}
      </div>

      {server && (
        <>
          <div className="mb-3 flex gap-1" role="tablist" aria-label="Телефон">
            {(['ios', 'android'] as Platform[]).map((p) => (
              <button
                key={p}
                type="button"
                role="tab"
                aria-selected={platform === p}
                onClick={() => setPlatform(p)}
                className={cn(
                  'flex h-7 items-center gap-1.5 rounded-full px-3 text-sm transition-colors',
                  platform === p ? 'bg-fg text-bg' : 'text-muted hover:bg-hover hover:text-fg',
                )}
              >
                {p === 'ios' ? <Apple className="size-3.5" /> : <Smartphone className="size-3.5" />}
                {p === 'ios' ? 'iPhone' : 'Android'}
              </button>
            ))}
          </div>

          {platform === 'ios' ? (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              <li>Настройки → Приложения → Контакты → Учётные записи → Новая учётная запись → Другое → «Учётная запись CardDAV»: сервер, пользователь и пароль — как выше.</li>
              <li>Календарь: Настройки → Приложения → Календарь → Учётные записи → Новая учётная запись → Другое → «Учётная запись CalDAV» с теми же данными.</li>
              {!server.isHttps && (
                <li>Если ругается на SSL: Дополнительно → выключить «Использовать SSL» и указать порт из адреса сервера.</li>
              )}
            </ol>
          ) : (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              <li>Установите DAVx⁵ (бесплатно в F-Droid, платно в Google Play).</li>
              <li>
                «Вход по URL и имени пользователя»: адрес{' '}
                <code className="rounded bg-hover px-1 text-[13px]">{server.origin}/dav/</code>.
              </li>
              <li>Включите синхронизацию адресной книги и календаря «PersonalCRM» — DAVx⁵ найдёт обе сам.</li>
            </ol>
          )}
          {!server.isHttps && (
            <p className="mt-3 text-xs text-faint">
              Без HTTPS пароль идёт по сети открыто, а iPhone может вовсе его не отправить. Подробно: docs/setup_phone.md
            </p>
          )}
        </>
      )}
    </div>
  );
}

function CopyValue({ value }: { value: string }) {
  const [isCopied, setIsCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(value);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 1500);
    } catch {
      // буфер обмена недоступен (http на чужом адресе) — значение видно и так
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="group inline-flex items-center gap-1.5 rounded px-1 font-mono text-[13px] hover:bg-hover"
      aria-label={`Скопировать ${value}`}
    >
      {value}
      {isCopied ? <Check className="size-3.5 text-accent" /> : <Copy className="size-3.5 text-faint opacity-0 group-hover:opacity-100" />}
    </button>
  );
}
