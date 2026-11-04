'use client';

import { useState } from 'react';
import { CalendarDays, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import type { Interaction } from '@/lib/api-crm';
import { cn } from '@/lib/utils';
import { KIND_META, formatWhen } from '@/components/contact/timeline-kinds';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/overlays';

const PREVIEW_CHARS = 220;

type Props = {
  item: Interaction;
  onEdit: () => void;
  onDelete: () => void;
};

export function TimelineItem({ item, onEdit, onDelete }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const meta = KIND_META[item.kind];
  const Icon = meta.icon;
  const isLong = item.body.length > PREVIEW_CHARS || item.body.split('\n').length > 3;
  const shown = isExpanded || !isLong ? item.body : `${item.body.slice(0, PREVIEW_CHARS).trimEnd()}…`;

  return (
    <li className="group flex gap-3 py-3">
      <span className={cn('mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full [&_svg]:size-4', meta.tone)}>
        <Icon aria-hidden />
        <span className="sr-only">{meta.label}</span>
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-2 text-[15px] font-medium">
              {item.title || meta.label}
              {item.read_only && (
                <span className="inline-flex items-center gap-1 rounded-full bg-crm-meeting/15 px-1.5 py-0.5 text-[11px] font-medium text-crm-meeting">
                  <CalendarDays className="size-3" /> Календарь
                </span>
              )}
            </div>
            <time dateTime={item.occurred_at} className="text-xs text-faint">
              {formatWhen(item.occurred_at)}
            </time>
          </div>
          {!item.read_only && (
            <Menu>
              <MenuTrigger asChild>
                <Button variant="ghost" size="icon" className="-mr-1 size-7 opacity-0 focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100" aria-label="Действия с записью">
                  <MoreHorizontal />
                </Button>
              </MenuTrigger>
              <MenuContent align="end">
                <MenuItem onSelect={onEdit}>
                  <Pencil /> Изменить
                </MenuItem>
                <MenuItem danger onSelect={onDelete}>
                  <Trash2 /> Удалить
                </MenuItem>
              </MenuContent>
            </Menu>
          )}
        </div>
        {item.body && (
          <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-muted">
            {shown}
            {isLong && (
              <button
                type="button"
                onClick={() => setIsExpanded((v) => !v)}
                className="ml-1 text-accent hover:text-accent-hover"
              >
                {isExpanded ? 'Свернуть' : 'Ещё'}
              </button>
            )}
          </p>
        )}
      </div>
    </li>
  );
}
