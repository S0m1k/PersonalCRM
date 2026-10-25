'use client';

/**
 * Календарь подключения на странице «Синхронизация»: включить/выключить, обновить,
 * либо переподключить аккаунт, если доступа к календарю нет (подключения до Sprint 7).
 */

import { useState } from 'react';
import { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { CalendarDays, KeyRound, Loader2, RefreshCw } from 'lucide-react';
import {
  reconnectProvider,
  triggerCalendarSync,
  updateConnection,
  type CalendarConnection,
  type SyncConnection,
} from '@/lib/api';
import { errorText, relativeTime } from '@/lib/utils';
import { Button } from '@/components/ui/button';

type Props = {
  connection: SyncConnection;
  onChange: () => void;
};

export function ConnectionCalendar({ connection, onChange }: Props) {
  const conn = connection as CalendarConnection;
  const { mutate } = useSWRConfig();
  const [isBusy, setIsBusy] = useState(false);

  async function run(action: () => Promise<void>) {
    setIsBusy(true);
    try {
      await action();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsBusy(false);
      onChange();
    }
  }

  const handleReconnect = () =>
    run(async () => {
      const { authorize_url } = await reconnectProvider(conn.provider as 'microsoft' | 'google', conn.id);
      window.location.assign(authorize_url);
    });

  const handleToggle = () =>
    run(async () => {
      await updateConnection(conn.id, { sync_calendar: !conn.sync_calendar });
    });

  const handleSync = () =>
    run(async () => {
      const { stats } = await triggerCalendarSync(conn.id);
      toast.success(`Календарь: новых ${stats.created}, изменений ${stats.updated + stats.deleted}`);
      void mutate((k) => typeof k === 'string' && k.startsWith('/api/calendar'));
    });

  if (!conn.calendar_access) {
    return (
      <div className="mb-2 flex items-center gap-2 rounded-md bg-tag-yellow/60 px-2.5 py-2 text-sm">
        <KeyRound className="size-4 shrink-0 text-muted" />
        <span className="flex-1 text-muted">Нет доступа к календарю</span>
        <Button size="sm" variant="outline" disabled={isBusy} onClick={() => void handleReconnect()}>
          {isBusy && <Loader2 className="animate-spin" />} Разрешить доступ
        </Button>
      </div>
    );
  }

  const status = !conn.sync_calendar
    ? 'Календарь выключен'
    : conn.calendar_last_sync
      ? `Календарь обновлён ${relativeTime(conn.calendar_last_sync)}`
      : 'Календарь ещё не синхронизирован';

  return (
    <div className="mb-2 flex items-center gap-2 rounded-md bg-sidebar px-2.5 py-2 text-sm">
      <CalendarDays className="size-4 shrink-0 text-faint" />
      <span className="flex-1 text-muted">{status}</span>
      {conn.sync_calendar && (
        <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => void handleSync()}>
          {isBusy ? <Loader2 className="animate-spin" /> : <RefreshCw />} Обновить
        </Button>
      )}
      <Button size="sm" variant="ghost" disabled={isBusy} onClick={() => void handleToggle()}>
        {conn.sync_calendar ? 'Выключить' : 'Включить'}
      </Button>
    </div>
  );
}
