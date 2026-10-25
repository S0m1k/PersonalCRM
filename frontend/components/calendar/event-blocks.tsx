'use client';

/**
 * Встречи в других разделах: «Сегодня» на главной и встречи с человеком в его карточке.
 */

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { ArrowUpRight, CalendarDays, Plus } from 'lucide-react';
import { eventsKey, type CalendarEvent } from '@/lib/api';
import { addDays, DAY_FMT, eventBounds, startOfDay } from '@/lib/calendar';
import { Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { EventDialog } from './event-dialog';
import { EventRow } from './event-row';
import type { PickedContact } from './contact-picker';

// Встречи с человеком: прошлые за полгода и будущие на год вперёд
const CONTACT_PAST_DAYS = 180;
const CONTACT_FUTURE_DAYS = 365;
const CONTACT_PAST_SHOWN = 3;

type DialogState = { event: CalendarEvent | null } | null;

export function TodayEvents() {
  const [today] = useState(() => startOfDay(new Date()));
  const { data: events, isLoading } = useSWR<CalendarEvent[]>(eventsKey({ start: today, end: addDays(today, 1) }));
  const [dialog, setDialog] = useState<DialogState>(null);

  return (
    <>
      {isLoading ? (
        <Skeleton className="h-10" />
      ) : events?.length ? (
        <div className="flex flex-col">
          {events.map((e) => (
            <EventRow key={e.id} event={e} day={today} onOpen={(event) => setDialog({ event })} isCompact />
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-md bg-sidebar px-3 py-3 text-sm text-muted">
          <CalendarDays className="size-5 shrink-0 text-faint" />
          <span className="flex-1">Сегодня встреч нет.</span>
          <Link href="/calendar" className="flex items-center gap-0.5 text-xs hover:text-fg">
            Календарь <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      )}
      <EventDialog open={dialog !== null} onOpenChange={(open) => !open && setDialog(null)} event={dialog?.event ?? null} />
    </>
  );
}

export function ContactEvents({ contact }: { contact: PickedContact }) {
  const [range] = useState(() => {
    const today = startOfDay(new Date());
    return { start: addDays(today, -CONTACT_PAST_DAYS), end: addDays(today, CONTACT_FUTURE_DAYS) };
  });
  const { data: events, isLoading } = useSWR<CalendarEvent[]>(eventsKey({ ...range, contactId: contact.id }));
  const [dialog, setDialog] = useState<DialogState>(null);
  const [initialContacts] = useState(() => [contact]);

  const [now] = useState(() => Date.now());
  const upcoming = events?.filter((e) => eventBounds(e).end.getTime() >= now) ?? [];
  const past = (events?.filter((e) => eventBounds(e).end.getTime() < now) ?? []).slice(-CONTACT_PAST_SHOWN).reverse();
  const open = (event: CalendarEvent) => setDialog({ event });

  return (
    <div>
      {isLoading ? (
        <Skeleton className="h-10" />
      ) : (
        <>
          {upcoming.map((e) => (
            <EventGroupRow key={e.id} event={e} onOpen={open} />
          ))}
          {upcoming.length === 0 && <p className="py-1 text-sm text-faint">Встреч не запланировано.</p>}
          {past.length > 0 && (
            <>
              <div className="mb-0.5 mt-3 text-xs font-medium text-faint">Недавно</div>
              {past.map((e) => (
                <EventGroupRow key={e.id} event={e} onOpen={open} />
              ))}
            </>
          )}
        </>
      )}
      <Button variant="ghost" size="sm" className="mt-1" onClick={() => setDialog({ event: null })}>
        <Plus /> Встреча
      </Button>
      <EventDialog
        open={dialog !== null}
        onOpenChange={(isOpen) => !isOpen && setDialog(null)}
        event={dialog?.event ?? null}
        initialContacts={initialContacts}
      />
    </div>
  );
}

/** Строка с датой над временем — для списков на много дней. */
function EventGroupRow({ event, onOpen }: { event: CalendarEvent; onOpen: (event: CalendarEvent) => void }) {
  const { start } = eventBounds(event);
  return (
    <div>
      <div className="pt-1 text-xs text-faint first-letter:uppercase">{DAY_FMT.format(start)}</div>
      <EventRow event={event} day={start} onOpen={onOpen} />
    </div>
  );
}
