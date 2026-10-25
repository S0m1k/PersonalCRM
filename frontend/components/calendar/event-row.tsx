'use client';

import { CircleHelp, MapPin } from 'lucide-react';
import type { CalendarEvent } from '@/lib/api';
import { timeRange } from '@/lib/calendar';
import { cn, plural } from '@/lib/utils';
import { GoogleMark, MicrosoftMark } from '@/components/app/icons';
import { Tag } from '@/components/ui/tag';

type Props = {
  event: CalendarEvent;
  /** День, в котором показываем событие (для многодневных — «до 12:00») */
  day?: Date;
  onOpen: (event: CalendarEvent) => void;
  isCompact?: boolean;
};

const SOURCE_MARK = { microsoft: MicrosoftMark, google: GoogleMark } as const;

/** Строка события: время, название, люди и сколько вопросов к ним ждут встречи. */
export function EventRow({ event, day, onOpen, isCompact = false }: Props) {
  const Mark = event.source === 'crm' ? null : SOURCE_MARK[event.source];
  const people = event.contacts.map((c) => c.name || 'Без имени').join(', ');
  return (
    <button
      type="button"
      onClick={() => onOpen(event)}
      className={cn(
        '-mx-2 flex w-[calc(100%+16px)] items-start gap-3 rounded px-2 text-left transition-colors hover:bg-hover',
        isCompact ? 'py-1.5' : 'py-2',
      )}
    >
      <span className={cn('tabular shrink-0 pt-px text-xs text-muted', isCompact ? 'w-12' : 'w-[88px]')}>
        {timeRange(event, day)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="truncate text-sm font-medium">{event.title}</span>
          {Mark && (
            <span className="shrink-0 opacity-70 [&_svg]:size-3.5" aria-label="Из внешнего календаря">
              <Mark />
            </span>
          )}
        </span>
        {(people || (!isCompact && event.location)) && (
          <span className="flex items-center gap-2 truncate text-xs text-muted">
            {people && <span className="truncate">{people}</span>}
            {!isCompact && event.location && (
              <span className="flex shrink-0 items-center gap-0.5 text-faint">
                <MapPin className="size-3" /> {event.location}
              </span>
            )}
          </span>
        )}
      </span>
      {event.questions.length > 0 && (
        <Tag color="blue" className="shrink-0" title="Открытые вопросы к участникам">
          <CircleHelp className="size-3" />
          {event.questions.length}
          {!isCompact && ` ${plural(event.questions.length, 'вопрос', 'вопроса', 'вопросов')}`}
        </Tag>
      )}
    </button>
  );
}
