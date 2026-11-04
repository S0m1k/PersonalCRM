'use client';

import { useState } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { Check, GitMerge, RefreshCw, X } from 'lucide-react';
import type { Contact } from '@/lib/api';
import { dismissDuplicate, duplicatesKey, mergeContacts, type DuplicatePair } from '@/lib/api-views';
import { cn, errorText, formatDate, fullName, plural } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { EmptyState, Page, PageHeader, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Tag } from '@/components/ui/tag';

const ROWS: { label: string; value: (c: Contact) => string }[] = [
  { label: 'Телефоны', value: (c) => c.phones.map((p) => p.value).join(', ') },
  { label: 'Email', value: (c) => c.emails.map((e) => e.value).join(', ') },
  { label: 'Компания', value: (c) => c.company },
  { label: 'Должность', value: (c) => c.position },
  { label: 'Город', value: (c) => c.city },
  { label: 'День рождения', value: (c) => (c.birthday ? formatDate(c.birthday) : '') },
  { label: 'Теги', value: (c) => c.tags.join(', ') },
  { label: 'Источник', value: (c) => c.sources.join(', ') || c.source },
  { label: 'Добавлен', value: (c) => formatDate(c.created_at.slice(0, 10)) },
];

/** Богаче заполненный контакт — вероятнее тот, что нужно оставить. */
function richness(c: Contact): number {
  return ROWS.slice(0, 7).filter((r) => r.value(c)).length;
}

export default function MergePage() {
  const { data, isLoading, isValidating, mutate } = useSWR<DuplicatePair[]>(duplicatesKey(), { revalidateOnFocus: false });
  const { mutate: mutateGlobal } = useSWRConfig();

  async function afterChange() {
    await mutate();
    void mutateGlobal((key) => typeof key === 'string' && (key.startsWith('/api/contacts') && key !== duplicatesKey() || key.startsWith('/api/home')));
  }

  return (
    <Page wide>
      <PageHeader
        icon={GitMerge}
        title="Слияние дублей"
        description="Похожие контакты по телефону, почте и имени. Выберите, какой оставить: недостающие данные подтянутся из второго."
        actions={
          <Button variant="outline" onClick={() => void mutate()} disabled={isValidating} aria-label="Обновить список дублей">
            <RefreshCw className={cn(isValidating && 'animate-spin')} /> Обновить
          </Button>
        }
      />

      {isLoading && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      )}

      {data && data.length === 0 && (
        <EmptyState icon={GitMerge} title="Дублей не найдено">
          Когда появятся похожие контакты, они покажутся здесь. Отклонённые пары больше не предлагаются.
        </EmptyState>
      )}

      {data && data.length > 0 && (
        <>
          <p className="mb-4 text-sm text-muted tabular">
            {data.length} {plural(data.length, 'пара', 'пары', 'пар')}
          </p>
          <div className="flex flex-col gap-6">
            {data.map((pair) => (
              <PairCard key={`${pair.a.id}|${pair.b.id}`} pair={pair} onDone={afterChange} />
            ))}
          </div>
        </>
      )}
    </Page>
  );
}

function PairCard({ pair, onDone }: { pair: DuplicatePair; onDone: () => Promise<void> }) {
  const { a, b } = pair;
  const [keepId, setKeepId] = useState(richness(b) > richness(a) ? b.id : a.id);
  const [isBusy, setIsBusy] = useState(false);

  async function run(action: () => Promise<unknown>, success: string) {
    setIsBusy(true);
    try {
      await action();
      toast.success(success);
      await onDone();
    } catch (err) {
      toast.error(errorText(err));
      setIsBusy(false);
    }
  }

  const other = keepId === a.id ? b : a;

  return (
    <article className="rounded-2xl border border-line bg-surface shadow-xs" aria-label={`${fullName(a)} и ${fullName(b)}`}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <Tag color={pair.score >= 90 ? 'orange' : 'yellow'}>Совпадение {pair.score}%</Tag>
        <span className="text-xs text-muted">{pair.reasons.join(' · ')}</span>
      </div>

      <div className="grid grid-cols-[110px_1fr_1fr] text-sm max-sm:grid-cols-[84px_1fr_1fr]">
        <div />
        {[a, b].map((c) => (
          <label key={c.id} className={cn('flex cursor-pointer items-center gap-2.5 border-l border-line p-3', keepId === c.id && 'bg-accent/5')}>
            <input type="radio" name={`keep-${a.id}`} checked={keepId === c.id} onChange={() => setKeepId(c.id)} className="size-4 accent-[rgb(var(--accent))]" />
            <Avatar name={fullName(c) || '?'} size="lg" />
            <span className="min-w-0">
              <Link href={`/contacts/${c.id}`} className="block truncate font-medium hover:underline">
                {fullName(c) || 'Без имени'}
              </Link>
              <span className="text-xs text-muted">{keepId === c.id ? 'Оставить' : 'Влить'}</span>
            </span>
          </label>
        ))}
        {ROWS.map((row) => {
          const [va, vb] = [row.value(a), row.value(b)];
          const differs = va !== vb;
          return (
            <div key={row.label} className="contents">
              <div className="border-t border-line px-3 py-2 text-xs text-muted">{row.label}</div>
              {[va, vb].map((v, i) => (
                <div key={i} className={cn('break-words border-l border-t border-line px-3 py-2', differs && v && 'font-medium')}>
                  {v || <span className="text-faint">—</span>}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      <div className="flex flex-wrap justify-end gap-2 border-t border-line p-3">
        <Button variant="ghost" disabled={isBusy} onClick={() => run(() => dismissDuplicate(a.id, b.id), 'Пара больше не предлагается')}>
          <X /> Не дубли
        </Button>
        <Button
          variant="primary"
          disabled={isBusy}
          onClick={() => run(() => mergeContacts(keepId, [other.id]), `Объединено: ${fullName(other) || 'контакт'} влит в ${fullName(keepId === a.id ? a : b) || 'контакт'}`)}
        >
          <Check /> Объединить
        </Button>
      </div>
    </article>
  );
}
