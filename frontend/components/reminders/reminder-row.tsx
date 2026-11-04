'use client';

import Link from 'next/link';
import { Check, MoreHorizontal, Pencil, Repeat, Trash2 } from 'lucide-react';
import { daysFromToday, dueLabel, REPEAT_LABELS, type Reminder } from '@/lib/api-reminders';
import { cn } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/overlays';

type Props = {
  reminder: Reminder;
  /** Без onToggle галочка неактивна (у выполненных) */
  onToggle?: (reminder: Reminder) => void;
  /** Без onEdit/onDelete меню не показывается (компактный вид на главной) */
  onEdit?: (reminder: Reminder) => void;
  onDelete?: (reminder: Reminder) => void;
};

export function ReminderRow({ reminder, onToggle, onEdit, onDelete }: Props) {
  const isDone = reminder.done_at !== null;
  const isOverdue = !isDone && daysFromToday(reminder.due_date) < 0;
  const hasMenu = Boolean(onEdit || onDelete);

  return (
    <li className="group -mx-2 flex items-start gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-hover/60">
      <button
        type="button"
        onClick={() => onToggle?.(reminder)}
        disabled={!onToggle}
        aria-label={isDone ? `Выполнено: ${reminder.title}` : `Отметить выполненным: ${reminder.title}`}
        className={cn(
          'mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-full border-[1.5px] transition-colors',
          isDone ? 'border-accent bg-accent text-accent-fg' : 'border-faint hover:border-accent',
        )}
      >
        {isDone && <Check className="size-3" strokeWidth={3} />}
      </button>

      <div className="min-w-0 flex-1">
        <div className={cn('text-sm', isDone && 'text-muted line-through')}>{reminder.title}</div>
        {reminder.note && <div className="mt-0.5 line-clamp-2 text-xs text-muted">{reminder.note}</div>}
        {reminder.contact_id && reminder.contact_name && (
          <Link
            href={`/contacts/${reminder.contact_id}`}
            className="mt-1 inline-flex h-6 max-w-full items-center gap-1.5 rounded-full bg-hover pl-0.5 pr-2 text-xs hover:bg-line"
          >
            <Avatar name={reminder.contact_name} size="sm" />
            <span className="truncate">{reminder.contact_name}</span>
          </Link>
        )}
      </div>

      <div className="flex shrink-0 items-center gap-2 pt-0.5 text-xs">
        {reminder.repeat !== 'none' && (
          <Repeat className="size-3.5 text-faint" aria-label={REPEAT_LABELS[reminder.repeat]} role="img" />
        )}
        <span className={cn(isOverdue ? 'font-medium text-danger' : 'text-muted')}>{dueLabel(reminder)}</span>
        {hasMenu && (
          <Menu>
            <MenuTrigger
              aria-label={`Действия: ${reminder.title}`}
              className="rounded p-1 text-faint opacity-0 hover:bg-line hover:text-fg focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100"
            >
              <MoreHorizontal className="size-4" />
            </MenuTrigger>
            <MenuContent align="end">
              {onEdit && (
                <MenuItem onSelect={() => onEdit(reminder)}>
                  <Pencil /> Изменить
                </MenuItem>
              )}
              {onDelete && (
                <MenuItem danger onSelect={() => onDelete(reminder)}>
                  <Trash2 /> Удалить
                </MenuItem>
              )}
            </MenuContent>
          </Menu>
        )}
      </div>
    </li>
  );
}
