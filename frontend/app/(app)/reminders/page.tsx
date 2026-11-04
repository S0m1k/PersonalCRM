'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { toast } from 'sonner';
import { BellRing, ChevronRight, Plus } from 'lucide-react';
import {
  completeReminder,
  deleteReminder,
  reminderGroup,
  remindersKey,
  type Reminder,
  type ReminderGroupId,
} from '@/lib/api-reminders';
import { cn, errorText } from '@/lib/utils';
import { EmptyState, Page, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { ReminderDialog } from '@/components/reminders/reminder-dialog';
import { ReminderRow } from '@/components/reminders/reminder-row';

const GROUPS: { id: ReminderGroupId; label: string; isDanger?: boolean }[] = [
  { id: 'overdue', label: 'Просрочено', isDanger: true },
  { id: 'today', label: 'Сегодня' },
  { id: 'week', label: 'На неделе' },
  { id: 'later', label: 'Позже' },
];

const ALL_KEY = remindersKey({ status: 'all' });

type DialogState = { reminder: Reminder | null } | null;

export default function RemindersPage() {
  const { data, isLoading, mutate } = useSWR<Reminder[]>(ALL_KEY);
  const [dialog, setDialog] = useState<DialogState>(null);
  const [isDoneOpen, setIsDoneOpen] = useState(false);

  const open = (data ?? []).filter((r) => r.done_at === null);
  const done = (data ?? []).filter((r) => r.done_at !== null).sort((a, b) => (b.done_at ?? '').localeCompare(a.done_at ?? ''));

  async function toggle(reminder: Reminder) {
    try {
      await completeReminder(reminder.id);
      await mutate();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function remove(reminder: Reminder) {
    try {
      await deleteReminder(reminder.id);
      await mutate();
      toast.success('Напоминание удалено');
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <Page>
      <header className="mb-8 animate-fade-up">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h1 className="font-display text-title">Напоминания</h1>
          <Button variant="primary" onClick={() => setDialog({ reminder: null })}>
            <Plus /> Добавить напоминание
          </Button>
        </div>
        <p className="mt-2 max-w-prose text-[13px] text-muted">
          Не забывайте о важном. Регулярное общение с людьми настраивается в{' '}
          <Link href="/keep-in-touch" className="text-accent underline-offset-2 hover:underline">
            Keep in Touch
          </Link>
          .
        </p>
      </header>

      {isLoading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : (
        <>
          {open.length === 0 && (
            <EmptyState icon={BellRing} title="Напоминаний пока нет">
              Добавьте напоминание — например, поздравить, позвонить или вернуться к разговору.
            </EmptyState>
          )}
          <div className="flex flex-col gap-7">
            {GROUPS.map((group) => {
              const items = open.filter((r) => reminderGroup(r.due_date) === group.id);
              if (items.length === 0) return null;
              return (
                <section key={group.id} aria-label={group.label}>
                  <h2 className={cn('mb-1 border-b border-line pb-1.5 text-[13px] font-medium', group.isDanger ? 'text-danger' : 'text-fg')}>
                    {group.label} <span className="font-normal text-faint">{items.length}</span>
                  </h2>
                  <ul>
                    {items.map((r) => (
                      <ReminderRow key={r.id} reminder={r} onToggle={toggle} onEdit={(x) => setDialog({ reminder: x })} onDelete={remove} />
                    ))}
                  </ul>
                </section>
              );
            })}
            {done.length > 0 && (
              <section aria-label="Выполнено">
                <button
                  type="button"
                  onClick={() => setIsDoneOpen((v) => !v)}
                  aria-expanded={isDoneOpen}
                  className="mb-1 flex w-full items-center gap-1 border-b border-line pb-1.5 text-left text-[13px] font-medium text-muted hover:text-fg"
                >
                  <ChevronRight className={cn('size-4 transition-transform', isDoneOpen && 'rotate-90')} />
                  Выполнено <span className="font-normal text-faint">{done.length}</span>
                </button>
                {isDoneOpen && (
                  <ul>
                    {done.map((r) => (
                      <ReminderRow key={r.id} reminder={r} onDelete={remove} />
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>
        </>
      )}

      <ReminderDialog
        open={dialog !== null}
        onOpenChange={(isOpen) => !isOpen && setDialog(null)}
        reminder={dialog?.reminder ?? null}
        onSaved={() => void mutate()}
      />
    </Page>
  );
}
