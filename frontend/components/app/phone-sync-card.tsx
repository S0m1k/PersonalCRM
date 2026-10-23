'use client';

/**
 * Карточка «Телефон» на странице синхронизации: как подключить iPhone / Android по CardDAV.
 * Пароль в интерфейс не отдаётся — он лежит в backend/.env (CARDDAV_PASSWORD).
 */

import { useState } from 'react';
import useSWR from 'swr';
import { Apple, Check, Copy, Smartphone } from 'lucide-react';
import type { CarddavStatus } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Tag } from '@/components/ui/tag';

const BACKEND_PORT = 8000;

type Platform = 'ios' | 'android';

function serverAddress(): string {
  if (typeof window === 'undefined') return '';
  const host = window.location.hostname;
  const isLocal = host === 'localhost' || host === '127.0.0.1';
  return isLocal ? `IP-этого-ПК:${BACKEND_PORT}` : `${host}:${BACKEND_PORT}`;
}

export function PhoneSyncCard() {
  const { data: status } = useSWR<CarddavStatus>('/api/carddav/status');
  const [platform, setPlatform] = useState<Platform>('ios');
  const server = serverAddress();

  return (
    <div className="mb-10 rounded-lg border border-line p-4">
      <div className="mb-2 flex items-center gap-2.5">
        <Smartphone className="size-6 text-muted" strokeWidth={1.6} />
        <span className="font-semibold">Телефон</span>
        {status && <Tag color={status.enabled ? 'green' : 'gray'}>{status.enabled ? 'включено' : 'выключено'}</Tag>}
      </div>
      <p className="mb-4 text-sm text-muted">
        Контакты CRM появятся в обычной «Звонилке» как отдельная адресная книга. Правки на телефоне сразу попадают в CRM и
        обратно. Удалённый на телефоне контакт уходит в корзину, а не пропадает насовсем.
      </p>

      {status && !status.enabled && (
        <p className="rounded-md bg-sidebar px-3 py-2 text-sm text-muted">
          Задайте <code className="rounded bg-hover px-1 text-[13px]">CARDDAV_PASSWORD</code> в{' '}
          <code className="rounded bg-hover px-1 text-[13px]">backend/.env</code> и перезапустите backend.
        </p>
      )}

      {status?.enabled && (
        <>
          <dl className="mb-4 grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-muted">Сервер</dt>
            <dd><CopyValue value={server} /></dd>
            <dt className="text-muted">Пользователь</dt>
            <dd><CopyValue value={status.username} /></dd>
            <dt className="text-muted">Пароль</dt>
            <dd className="text-muted">
              строка <code className="rounded bg-hover px-1 text-[13px]">CARDDAV_PASSWORD</code> в backend/.env
            </dd>
          </dl>

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
              <li>Настройки → Приложения → Контакты → Учётные записи → Новая учётная запись → Другое.</li>
              <li>«Учётная запись CardDAV»: сервер, пользователь и пароль — как выше.</li>
              <li>Если ругается на SSL: Дополнительно → выключить «Использовать SSL», порт {BACKEND_PORT}.</li>
            </ol>
          ) : (
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              <li>Установите DAVx⁵ (бесплатно в F-Droid, платно в Google Play).</li>
              <li>«Вход по URL и имени пользователя»: адрес <code className="rounded bg-hover px-1 text-[13px]">http://{server}/dav/</code>.</li>
              <li>Включите синхронизацию адресной книги «PersonalCRM».</li>
            </ol>
          )}
          <p className="mt-3 text-xs text-faint">
            Пока CRM работает на этом ПК, телефон должен быть в той же Wi-Fi сети. Подробно: docs/setup_phone.md
          </p>
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
