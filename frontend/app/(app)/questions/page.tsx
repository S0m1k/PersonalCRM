'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { CircleHelp, Inbox, PartyPopper } from 'lucide-react';
import { toast } from 'sonner';
import { deleteQuestion, updateQuestion, type Question, type QuestionStatus, type QuestionUpdate } from '@/lib/api';
import { cn, errorText } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { EmptyState, Page, PageHeader, Skeleton } from '@/components/app/page';
import { QuestionItem } from '@/components/contact/questions-panel';

const FILTERS: { value: QuestionStatus; label: string }[] = [
  { value: 'open', label: 'Открытые' },
  { value: 'answered', label: 'Отвеченные' },
  { value: 'dropped', label: 'Неактуальные' },
];

export default function QuestionsPage() {
  const [status, setStatus] = useState<QuestionStatus>('open');
  const key = `/api/questions?status=${status}`;
  const { data: questions, mutate } = useSWR<Question[]>(key);
  const { mutate: mutateGlobal } = useSWRConfig();

  const groups = useMemo(() => {
    const byContact = new Map<string, { name: string; items: Question[] }>();
    for (const q of questions ?? []) {
      const group = byContact.get(q.contact_id) ?? { name: q.contact_name || 'Без имени', items: [] };
      byContact.set(q.contact_id, { ...group, items: [...group.items, q] });
    }
    return [...byContact.entries()];
  }, [questions]);

  function refreshOthers() {
    void mutateGlobal((k) => typeof k === 'string' && (k.startsWith('/api/home') || (k.startsWith('/api/questions') && k !== key)));
  }

  async function handleUpdate(id: string, data: QuestionUpdate) {
    try {
      await updateQuestion(id, data);
      await mutate();
      refreshOthers();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleDelete(id: string) {
    try {
      await deleteQuestion(id);
      await mutate();
      refreshOthers();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <Page>
      <PageHeader
        icon={CircleHelp}
        title="Вопросы"
        description="Что вы хотели узнать у людей. Отметьте вопрос — и запишите ответ, он останется в карточке."
      />

      <div className="mb-6 flex gap-1" role="tablist">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            type="button"
            role="tab"
            aria-selected={status === f.value}
            onClick={() => setStatus(f.value)}
            className={cn(
              'h-7 rounded-full px-3 text-sm transition-colors',
              status === f.value ? 'bg-fg text-bg' : 'text-muted hover:bg-hover hover:text-fg',
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {!questions ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <EmptyState icon={status === 'open' ? PartyPopper : Inbox} title={status === 'open' ? 'Все вопросы закрыты' : 'Здесь пусто'}>
          {status === 'open' && 'Новый вопрос добавляется в карточке человека.'}
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-7">
          {groups.map(([contactId, group]) => (
            <section key={contactId}>
              <Link
                href={`/contacts/${contactId}?tab=questions`}
                className="-mx-2 mb-1 inline-flex items-center gap-2 rounded px-2 py-1 text-sm font-semibold hover:bg-hover"
              >
                <Avatar name={group.name} size="sm" />
                {group.name}
                <span className="font-normal text-faint">{group.items.length}</span>
              </Link>
              <div className="border-l border-line pl-3">
                {group.items.map((q) => (
                  <QuestionItem key={q.id} question={q} onUpdate={handleUpdate} onDelete={handleDelete} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </Page>
  );
}
