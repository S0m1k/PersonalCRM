'use client';

/**
 * Календарь (/calendar): неделя или список встреч, создание и правка, синхронизация
 * с Outlook / Google. Подключения без доступа к календарю просим переподключить.
 */

import { useState } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { CalendarDays, ChevronLeft, ChevronRight, KeyRound, List, Loader2, Plus, RefreshCw, Rows3 } from 'lucide-react';
import {
  reconnectProvider,
  triggerCalendarSync,
  eventsKey,
  type CalendarConnection,
  type CalendarEvent,
} from '@/lib/api';
import { addDays, DAY_FMT, occursOn, sameDay, SHORT_DAY_FMT, startOfWeek, weekLabel } from '@/lib/calendar';
import { cn, errorText } from '@/lib/utils';
import { EventDialog } from '@/components/calendar/event-dialog';
import { EventRow } from '@/components/calendar/event-row';
import { EmptyState, Page, PageHeader, SectionTitle, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';

type View = 'week' | 'list';

const PROVIDER_NAMES: Record<string, string> = { microsoft: 'Outlook', google: 'Google' };

type DialogState = { event: CalendarEvent | null; day?: Date } | null;

export default function CalendarPage() {
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [view, setView] = useState<View>('week');
  const [dialog, setDialog] = useState<DialogState>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const { mutate } = useSWRConfig();

  const weekEnd = addDays(weekStart, 7);
  const { data: events, isLoading } = useSWR<CalendarEvent[]>(eventsKey({ start: weekStart, end: weekEnd }));
  const { data: connections = [] } = useSWR<CalendarConnection[]>('/api/sync/connections');

  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const today = new Date();
  const syncable = connections.filter((c) => c.calendar_access && c.sync_calendar && PROVIDER_NAMES[c.provider]);
  const needConsent = connections.filter((c) => !c.calendar_access && PROVIDER_NAMES[c.provider]);

  async function handleSync() {
    setIsSyncing(true);
    try {
      let created = 0;
      let updated = 0;
      for (const conn of syncable) {
        const { stats } = await triggerCalendarSync(conn.id);
        created += stats.created;
        updated += stats.updated + stats.deleted;
      }
      toast.success(`Календарь обновлён: новых ${created}, изменений ${updated}`);
      void mutate((k) => typeof k === 'string' && (k.startsWith('/api/calendar') || k === '/api/sync/connections'));
    } catch (err) {
      toast.error(errorText(err));
      void mutate('/api/sync/connections');
    } finally {
      setIsSyncing(false);
    }
  }

  async function handleReconnect(conn: CalendarConnection) {
    try {
      const { authorize_url } = await reconnectProvider(conn.provider as 'microsoft' | 'google', conn.id);
      window.location.assign(authorize_url);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  const openEvent = (event: CalendarEvent) => setDialog({ event });

  return (
    <Page wide>
      <PageHeader
        icon={CalendarDays}
        title="Календарь"
        description="Встречи привязаны к людям: на встрече видны вопросы, которые вы хотели им задать."
        actions={
          <>
            {syncable.length > 0 && (
              <Button variant="ghost" disabled={isSyncing} onClick={() => void handleSync()}>
                {isSyncing ? <Loader2 className="animate-spin" /> : <RefreshCw />} Обновить
              </Button>
            )}
            <Button variant="primary" onClick={() => setDialog({ event: null })}>
              <Plus /> Встреча
            </Button>
          </>
        }
      />

      {needConsent.map((conn) => (
        <div key={conn.id} className="mb-4 flex flex-wrap items-center gap-3 rounded-md bg-tag-yellow/60 px-3 py-2.5 text-sm">
          <KeyRound className="size-4 shrink-0 text-muted" />
          <span className="flex-1">
            {PROVIDER_NAMES[conn.provider]} подключён без доступа к календарю. Переподключите аккаунт и разрешите
            доступ — контакты и настройки сохранятся.
          </span>
          <Button size="sm" variant="outline" onClick={() => void handleReconnect(conn)}>
            Разрешить доступ
          </Button>
        </div>
      ))}

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button size="icon" variant="ghost" aria-label="Предыдущая неделя" onClick={() => setWeekStart(addDays(weekStart, -7))}>
          <ChevronLeft />
        </Button>
        <Button size="icon" variant="ghost" aria-label="Следующая неделя" onClick={() => setWeekStart(addDays(weekStart, 7))}>
          <ChevronRight />
        </Button>
        <Button size="sm" variant="outline" onClick={() => setWeekStart(startOfWeek(new Date()))}>
          Сегодня
        </Button>
        <h2 className="ml-1 text-base font-semibold">{weekLabel(weekStart)}</h2>
        <div className="ml-auto flex rounded border border-line p-0.5" role="group" aria-label="Вид">
          {(
            [
              ['week', 'Неделя', Rows3],
              ['list', 'Список', List],
            ] as const
          ).map(([value, label, Icon]) => (
            <button
              key={value}
              type="button"
              aria-pressed={view === value}
              onClick={() => setView(value)}
              className={cn(
                'flex h-6 items-center gap-1 rounded-[3px] px-2 text-[13px] text-muted transition-colors hover:text-fg [&_svg]:size-3.5',
                view === value && 'bg-hover font-medium text-fg',
              )}
            >
              <Icon /> {label}
            </button>
          ))}
        </div>
      </div>

      {isLoading || !events ? (
        <Skeleton className="h-64" />
      ) : view === 'week' ? (
        <div className="grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
          {days.map((day) => {
            const dayEvents = events.filter((e) => occursOn(e, day));
            const isToday = sameDay(day, today);
            return (
              <section key={day.toISOString()} className="group flex min-h-28 flex-col bg-bg p-2 md:min-h-64">
                <div className="mb-1 flex items-center justify-between">
                  <span className={cn('text-xs capitalize text-muted', isToday && 'font-semibold text-fg')}>
                    {isToday ? (
                      <span className="rounded-[3px] bg-accent px-1 py-px text-accent-fg">{SHORT_DAY_FMT.format(day)}</span>
                    ) : (
                      SHORT_DAY_FMT.format(day)
                    )}
                  </span>
                  <button
                    type="button"
                    onClick={() => setDialog({ event: null, day })}
                    className="rounded p-0.5 text-faint opacity-0 transition-opacity hover:bg-hover hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
                    aria-label={`Встреча на ${DAY_FMT.format(day)}`}
                  >
                    <Plus className="size-3.5" />
                  </button>
                </div>
                <div className="flex flex-col">
                  {dayEvents.map((e) => (
                    <EventRow key={e.id} event={e} day={day} onOpen={openEvent} isCompact />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <AgendaList days={days} events={events} onOpen={openEvent} />
      )}

      <EventDialog
        open={dialog !== null}
        onOpenChange={(open) => !open && setDialog(null)}
        event={dialog?.event ?? null}
        initialDay={dialog?.day}
      />
    </Page>
  );
}

function AgendaList({
  days,
  events,
  onOpen,
}: {
  days: Date[];
  events: CalendarEvent[];
  onOpen: (event: CalendarEvent) => void;
}) {
  const filled = days.map((day) => ({ day, items: events.filter((e) => occursOn(e, day)) })).filter((d) => d.items.length);
  if (filled.length === 0) {
    return (
      <EmptyState icon={CalendarDays} title="На этой неделе встреч нет">
        Создайте встречу или подключите календарь Outlook / Google в «Синхронизации».
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {filled.map(({ day, items }) => (
        <section key={day.toISOString()}>
          <SectionTitle>
            <span className="first-letter:uppercase">{DAY_FMT.format(day)}</span>
          </SectionTitle>
          {items.map((e) => (
            <EventRow key={e.id} event={e} day={day} onOpen={onOpen} />
          ))}
        </section>
      ))}
    </div>
  );
}
