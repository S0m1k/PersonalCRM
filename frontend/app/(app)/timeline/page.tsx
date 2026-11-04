'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import useSWRInfinite from 'swr/infinite';
import { History, Plus } from 'lucide-react';
import { fetcher } from '@/lib/api';
import { interactionsKey, type InteractionKind, type InteractionPage } from '@/lib/api-crm';
import { errorText } from '@/lib/utils';
import { EmptyState, Page, PageHeader, Skeleton } from '@/components/app/page';
import type { PickedContact } from '@/components/calendar/contact-picker';
import {
  InteractionComposer,
  InteractionRow,
  INTERACTION_KINDS,
  monthKey,
  monthLabel,
  useContactsByIds,
} from '@/components/interactions';
import { DisplayPopover, FilterPopover, SearchBox } from '@/components/timeline/timeline-filters';
import { useUrlState } from '@/components/timeline/use-url-state';
import { Button } from '@/components/ui/button';

const PAGE_SIZE = 30;

function parseKinds(raw: string): InteractionKind[] {
  return raw.split(',').filter((k): k is InteractionKind => k in INTERACTION_KINDS);
}

/** Границы периода в ISO: «с» — начало дня, «по» — конец дня, по местному времени. */
function rangeToIso(from: string, to: string): { from?: string; to?: string } {
  return {
    from: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
    to: to ? new Date(`${to}T23:59:59.999`).toISOString() : undefined,
  };
}

function TimelineView() {
  const url = useUrlState();
  const kinds = parseKinds(url.get('kinds'));
  const contactIds = url.get('contacts').split(',').filter(Boolean);
  const from = url.get('from');
  const to = url.get('to');
  const q = url.get('q');
  const includeEvents = url.get('events') !== '0';

  const loadedContacts = useContactsByIds(contactIds);
  // Имена только что выбранных людей — чтобы плашки не мигали, пока контакты догружаются
  const [pickedNames, setPickedNames] = useState<Record<string, string>>({});
  const contacts: PickedContact[] = contactIds.map((id) => ({
    id,
    name: pickedNames[id] ?? loadedContacts.find((c) => c.id === id)?.name ?? '…',
  }));

  const [isComposing, setIsComposing] = useState(false);

  const range = rangeToIso(from, to);
  const getKey = (index: number, prev: InteractionPage | null) => {
    if (prev && !prev.next_cursor) return null;
    return interactionsKey({
      kind: kinds.length ? kinds : undefined,
      contact_id: contactIds.length ? contactIds : undefined,
      ...range,
      q: q || undefined,
      include_events: includeEvents,
      limit: PAGE_SIZE,
      cursor: index > 0 ? (prev?.next_cursor ?? undefined) : undefined,
    });
  };
  const { data, error, size, setSize, isLoading, isValidating } = useSWRInfinite<InteractionPage>(
    getKey,
    (key: string) => fetcher<InteractionPage>(key),
    { revalidateFirstPage: true },
  );

  const items = useMemo(() => (data ?? []).flatMap((p) => p.items), [data]);
  const hasMore = Boolean(data && data[data.length - 1]?.next_cursor);
  const isLoadingMore = isValidating && size > (data?.length ?? 0);

  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = sentinel.current;
    if (!node || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !isValidating) void setSize((s) => s + 1);
      },
      { rootMargin: '300px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, isValidating, setSize, items.length]);

  const commitSearch = useCallback((value: string) => url.set({ q: value }), [url]);

  const activeFilters = (kinds.length ? 1 : 0) + (contactIds.length ? 1 : 0) + (from || to ? 1 : 0);
  const isFiltered = activeFilters > 0 || q !== '';

  return (
    <Page>
      <PageHeader
        title="Timeline"
        description="Встретились с кем-то? Запишите — чтобы помнить, на чём остановились"
        actions={
          <Button variant="primary" onClick={() => setIsComposing(true)}>
            <Plus /> Добавить заметку
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center justify-end gap-2">
        <SearchBox value={q} onCommit={commitSearch} />
        <FilterPopover
          kinds={kinds}
          contacts={contacts}
          from={from}
          to={to}
          activeCount={activeFilters}
          onKinds={(next) => url.set({ kinds: next.join(',') })}
          onContacts={(next) => {
            setPickedNames((prev) => ({ ...prev, ...Object.fromEntries(next.map((c) => [c.id, c.name])) }));
            url.set({ contacts: next.map((c) => c.id).join(',') });
          }}
          onRange={(f, t) => url.set({ from: f, to: t })}
        />
        <DisplayPopover includeEvents={includeEvents} onChange={(v) => url.set({ events: v ? '' : '0' })} />
      </div>

      {error ? (
        <EmptyState icon={History} title="Не удалось загрузить ленту">
          {errorText(error)}
        </EmptyState>
      ) : isLoading ? (
        <div className="space-y-3" aria-busy>
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-12 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState icon={History} title={isFiltered ? 'Ничего не найдено' : 'Пока ничего не записано'}>
          {isFiltered ? 'Попробуйте изменить фильтры или поиск.' : 'Встретились с кем-то? Запишите — чтобы помнить, на чём остановились.'}
          {!isFiltered && (
            <div className="mt-4">
              <Button variant="primary" onClick={() => setIsComposing(true)}>
                <Plus /> Добавить заметку
              </Button>
            </div>
          )}
        </EmptyState>
      ) : (
        <div>
          {items.map((item, i) => (
            <div key={item.id}>
              {(i === 0 || monthKey(items[i - 1].occurred_at) !== monthKey(item.occurred_at)) && (
                <h2 className="mb-1 mt-6 border-b border-line pb-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted first:mt-0">
                  {monthLabel(item.occurred_at)}
                </h2>
              )}
              <ul>
                <InteractionRow interaction={item} />
              </ul>
            </div>
          ))}
          <div ref={sentinel} className="h-8" aria-hidden />
          {isLoadingMore && <Skeleton className="h-12 w-full" />}
          {hasMore && !isLoadingMore && (
            <div className="flex justify-center">
              <Button variant="ghost" size="sm" onClick={() => void setSize(size + 1)}>
                Показать ещё
              </Button>
            </div>
          )}
        </div>
      )}

      {isComposing && <InteractionComposer open onOpenChange={setIsComposing} />}
    </Page>
  );
}

export default function TimelinePage() {
  return (
    <Suspense fallback={null}>
      <TimelineView />
    </Suspense>
  );
}
