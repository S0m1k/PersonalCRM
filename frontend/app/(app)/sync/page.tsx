'use client';

/**
 * Синхронизация (/sync): подключение Outlook / Google, ручной запуск, история.
 */

import { useEffect, useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { History, Loader2, MoreHorizontal, RefreshCw, Unplug } from 'lucide-react';
import {
  ApiError,
  connectGoogle,
  connectMicrosoft,
  deleteConnection,
  triggerSync,
  type SyncConnection,
  type SyncLogEntry,
} from '@/lib/api';
import { errorText, relativeTime } from '@/lib/utils';
import { GoogleMark, MicrosoftMark } from '@/components/app/icons';
import { EmptyState, Page, PageHeader, SectionTitle, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/overlays';
import { Tag } from '@/components/ui/tag';

type Provider = 'microsoft' | 'google';

const PROVIDERS: Record<Provider, { name: string; logo: typeof GoogleMark; hint: string }> = {
  microsoft: { name: 'Outlook', logo: MicrosoftMark, hint: 'Контакты Microsoft 365 / Outlook.com — они же в телефоне, если он синхронизирован с Outlook' },
  google: { name: 'Google', logo: GoogleMark, hint: 'Google Контакты и всё, что сохранено на Android' },
};

const ACTION_LABELS: Record<string, string> = {
  full_sync: 'Полная синхронизация',
  delta_sync: 'Изменения',
  scheduled: 'По расписанию',
  webhook: 'Уведомление Outlook',
  manual: 'Вручную',
};

const ERROR_TEXT: Record<string, string> = {
  invalid_state: 'Вход занял слишком долго или открыт из старой вкладки. Нажмите «Подключить» ещё раз.',
  access_denied: 'Доступ не выдан — вход был отменён.',
  token_exchange_failed: 'Не удалось получить доступ у провайдера. Проверьте ключи в backend/.env.',
};

export default function SyncPage() {
  const { data: connections, mutate: mutateConnections } = useSWR<SyncConnection[]>('/api/sync/connections');
  const { data: log, mutate: mutateLog } = useSWR<SyncLogEntry[]>('/api/sync/log');
  const { mutate: mutateGlobal } = useSWRConfig();
  const [busyId, setBusyId] = useState<string | null>(null);
  const [setupProvider, setSetupProvider] = useState<Provider | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get('connected') as Provider | null;
    const error = params.get('error');
    if (connected) toast.success(`${PROVIDERS[connected]?.name ?? connected} подключён`);
    if (error) toast.error(ERROR_TEXT[error] ?? `Ошибка подключения: ${error}`);
    if (connected || error) window.history.replaceState(null, '', '/sync');
  }, []);

  async function handleConnect(provider: Provider) {
    setBusyId(provider);
    try {
      const { authorize_url } = provider === 'microsoft' ? await connectMicrosoft() : await connectGoogle();
      window.location.href = authorize_url;
    } catch (err) {
      setBusyId(null);
      if (err instanceof ApiError && err.status === 501) setSetupProvider(provider);
      else toast.error(errorText(err));
    }
  }

  async function handleSync(connection: SyncConnection) {
    setBusyId(connection.id);
    try {
      const { stats } = await triggerSync(connection.id);
      toast.success(`Готово: новых ${stats.created}, обновлено ${stats.updated + stats.merged}, ошибок ${stats.errors}`);
      void mutateConnections();
      void mutateLog();
      void mutateGlobal((k) => typeof k === 'string' && (k.startsWith('/api/contacts') || k.startsWith('/api/home')));
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleDisconnect(connection: SyncConnection) {
    try {
      await deleteConnection(connection.id);
      toast.success('Отключено. Контакты в CRM остались.');
      void mutateConnections();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <Page>
      <PageHeader
        icon={RefreshCw}
        title="Синхронизация"
        description="Подключите аккаунт один раз — дальше контакты обновляются сами каждые несколько минут, а правки из CRM уходят обратно."
      />

      <div className="mb-10 grid gap-3 sm:grid-cols-2">
        {(Object.keys(PROVIDERS) as Provider[]).map((provider) => {
          const info = PROVIDERS[provider];
          const linked = connections?.filter((c) => c.provider === provider) ?? [];
          return (
            <div key={provider} className="flex flex-col rounded-lg border border-line p-4">
              <div className="mb-2 flex items-center gap-2.5">
                <info.logo />
                <span className="font-semibold">{info.name}</span>
                {linked.length > 0 && <Tag color="green">подключён</Tag>}
              </div>
              <p className="mb-4 flex-1 text-sm text-muted">{info.hint}</p>

              {linked.map((c) => (
                <div key={c.id} className="mb-2 flex items-center gap-2 rounded-md bg-sidebar px-2.5 py-2 text-sm">
                  <span className="flex-1 text-muted">
                    {c.contacts_last_sync ? `Обновлено ${relativeTime(c.contacts_last_sync)}` : 'Ещё не синхронизировано'}
                  </span>
                  <Button size="sm" variant="ghost" disabled={busyId === c.id} onClick={() => handleSync(c)}>
                    {busyId === c.id ? <Loader2 className="animate-spin" /> : <RefreshCw />} Обновить
                  </Button>
                  <Menu>
                    <MenuTrigger asChild>
                      <Button size="icon" variant="ghost" aria-label="Действия">
                        <MoreHorizontal />
                      </Button>
                    </MenuTrigger>
                    <MenuContent align="end">
                      <MenuItem danger onSelect={() => handleDisconnect(c)}>
                        <Unplug /> Отключить
                      </MenuItem>
                    </MenuContent>
                  </Menu>
                </div>
              ))}

              {linked.length === 0 && (
                <Button variant="primary" className="self-start" disabled={busyId === provider} onClick={() => handleConnect(provider)}>
                  {busyId === provider && <Loader2 className="animate-spin" />} Подключить {info.name}
                </Button>
              )}
            </div>
          );
        })}
      </div>

      <SectionTitle>История</SectionTitle>
      {!log ? (
        <Skeleton className="h-24" />
      ) : log.length === 0 ? (
        <EmptyState icon={History} title="Синхронизаций ещё не было" />
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted [&>th]:h-8 [&>th]:font-normal">
              <th>Что</th>
              <th className="text-right">Новых</th>
              <th className="text-right">Слито</th>
              <th className="text-right">Ошибок</th>
              <th className="text-right">Когда</th>
            </tr>
          </thead>
          <tbody>
            {log.map((entry) => (
              <tr key={entry.id} className="tabular [&>td]:h-9 [&>td]:border-t [&>td]:border-line">
                <td>{ACTION_LABELS[entry.action] ?? entry.action}</td>
                <td className="text-right">{entry.stats.created}</td>
                <td className="text-right">{entry.stats.merged + entry.stats.updated}</td>
                <td className="text-right">{entry.stats.errors ? <Tag color="red">{entry.stats.errors}</Tag> : 0}</td>
                <td className="text-right text-muted">{relativeTime(entry.started_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <Dialog open={setupProvider !== null} onOpenChange={(open) => !open && setSetupProvider(null)}>
        <DialogContent
          title={`${setupProvider ? PROVIDERS[setupProvider].name : ''} ещё не настроен`}
          description="Нужно один раз зарегистрировать приложение и вписать ключи в backend/.env."
        >
          <ol className="list-decimal space-y-1.5 pl-5 text-sm">
            <li>
              Пройдите инструкцию <code className="rounded bg-hover px-1 text-[13px]">docs/setup_oauth.md</code>.
            </li>
            <li>Впишите ключи в <code className="rounded bg-hover px-1 text-[13px]">backend/.env</code>.</li>
            <li>
              Перезапустите backend:{' '}
              <code className="rounded bg-hover px-1 text-[13px]">docker compose up -d --force-recreate backend</code>
            </li>
          </ol>
          <div className="mt-5 flex justify-end">
            <Button variant="primary" onClick={() => setSetupProvider(null)}>
              Понятно
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
