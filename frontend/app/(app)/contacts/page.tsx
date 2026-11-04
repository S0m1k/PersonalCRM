'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import useSWRInfinite from 'swr/infinite';
import { toast } from 'sonner';
import { Plus, SearchX, UserPlus } from 'lucide-react';
import { deleteContact, updateContact, type Contact, type ContactUpdate } from '@/lib/api';
import { groupsKey, tagsKey, type Group, type TagCount } from '@/lib/api-crm';
import { createView, updateView, viewsKey, type ContactView } from '@/lib/api-views';
import {
  DEFAULT_COLUMNS,
  FILTER_KEYS,
  activeFilterCount,
  parseState,
  stateToParams,
  stateToQuery,
  type ColumnId,
  type FilterKey,
  type ListState,
} from '@/lib/contact-view';
import { errorText, plural } from '@/lib/utils';
import { useAppActions } from '@/components/app/app-shell';
import { EmptyState, Page, Skeleton } from '@/components/app/page';
import { BulkBar } from '@/components/contacts/bulk-bar';
import { ContactsTable } from '@/components/contacts/contacts-table';
import { ContactsToolbar } from '@/components/contacts/contacts-toolbar';
import { SaveViewDialog } from '@/components/contacts/save-view-dialog';
import { Button } from '@/components/ui/button';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 250;

export default function ContactsPage() {
  return (
    <Suspense fallback={<Page wide><Skeleton className="h-64" /></Page>}>
      <ContactsList />
    </Suspense>
  );
}

function ContactsList() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { mutate: mutateGlobal } = useSWRConfig();
  const { newContact } = useAppActions();

  const viewId = params.get('view');
  const { data: views = [] } = useSWR<ContactView[]>(viewsKey());
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());
  const { data: tags = [] } = useSWR<TagCount[]>(tagsKey());
  const activeView = views.find((v) => v.id === viewId);

  const state = useMemo(() => parseState(new URLSearchParams(params.toString()), activeView), [params, activeView]);
  const columns = (state.columns ?? DEFAULT_COLUMNS) as ColumnId[];
  const groupsById = useMemo(() => new Map(groups.map((g) => [g.id, g])), [groups]);

  const go = useCallback(
    (next: ListState) => {
      const qs = stateToParams(next, viewId).toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [router, pathname, viewId],
  );

  // Поиск: локальный текст, в URL уходит с задержкой
  const [searchText, setSearchText] = useState(state.q);
  useEffect(() => setSearchText(state.q), [state.q]);
  useEffect(() => {
    if (searchText.trim() === state.q) return;
    const id = setTimeout(() => go({ ...state, q: searchText.trim() }), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [searchText, state, go]);

  const query = stateToQuery(state).toString();
  const {
    data: pages,
    size,
    setSize,
    isLoading,
    isValidating,
    mutate: mutateList,
  } = useSWRInfinite<Contact[]>(
    (index, previous) => (previous && previous.length < PAGE_SIZE ? null : `/api/contacts/?${query}${query ? '&' : ''}limit=${PAGE_SIZE}&skip=${index * PAGE_SIZE}`),
    { revalidateFirstPage: false, keepPreviousData: true },
  );
  const { data: total } = useSWR<{ count: number }>(`/api/contacts/count${query ? `?${query}` : ''}`);
  const contacts = useMemo(() => pages?.flat(), [pages]);
  const hasMore = Boolean(pages && pages[pages.length - 1]?.length === PAGE_SIZE);

  const refreshAll = useCallback(async () => {
    await mutateList();
    void mutateGlobal((key) => typeof key === 'string' && (key.startsWith('/api/contacts/count') || key.startsWith('/api/home') || key === groupsKey() || key === tagsKey()));
  }, [mutateList, mutateGlobal]);

  // ---- выбор и массовые действия
  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [isBusy, setIsBusy] = useState(false);
  useEffect(() => setSelected(new Set()), [query]);

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const toggleAll = () =>
    setSelected((prev) => (contacts && contacts.every((c) => prev.has(c.id)) ? new Set() : new Set(contacts?.map((c) => c.id))));

  async function handleUpdate(id: string, patch: ContactUpdate) {
    try {
      await updateContact(id, patch);
      await refreshAll();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function runBulk(label: string, change: (c: Contact) => ContactUpdate | null) {
    const targets = (contacts ?? []).filter((c) => selected.has(c.id));
    setIsBusy(true);
    try {
      const results = await Promise.allSettled(
        targets.map((c) => {
          const patch = change(c);
          return patch ? updateContact(c.id, patch) : Promise.resolve(null);
        }),
      );
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed) toast.error(`${label}: не удалось у ${failed} из ${targets.length}`);
      else toast.success(`${label}: ${targets.length} ${plural(targets.length, 'контакт', 'контакта', 'контактов')}`);
      await refreshAll();
    } finally {
      setIsBusy(false);
    }
  }

  async function bulkDelete() {
    const ids = [...selected];
    setIsBusy(true);
    try {
      const results = await Promise.allSettled(ids.map((id) => deleteContact(id)));
      const failed = results.filter((r) => r.status === 'rejected').length;
      if (failed) toast.error(`Не удалось удалить ${failed} из ${ids.length}`);
      else toast.success(`Удалено: ${ids.length}`);
      setSelected(new Set());
      await refreshAll();
    } finally {
      setIsBusy(false);
    }
  }

  // ---- фильтры, виды
  const setFilter = (key: FilterKey, value: string) => {
    const filters = { ...state.filters };
    if (value) filters[key] = value;
    else delete filters[key];
    go({ ...state, filters });
  };
  const [isViewDialogOpen, setIsViewDialogOpen] = useState(false);
  useEffect(() => {
    if (params.get('newview')) {
      setIsViewDialogOpen(true);
      const rest = new URLSearchParams(params.toString());
      rest.delete('newview');
      router.replace(rest.toString() ? `${pathname}?${rest}` : pathname);
    }
  }, [params, pathname, router]);

  const viewPayload = () => ({
    filters: Object.fromEntries(FILTER_KEYS.filter((k) => state.filters[k]).map((k) => [k, state.filters[k] as string])),
    sort: state.sort,
    columns: state.columns ?? [],
  });

  async function saveView(name: string, emoji: string) {
    try {
      const view = await createView({ name, emoji, ...viewPayload() });
      await mutateGlobal(viewsKey());
      router.push(`${pathname}?view=${view.id}`);
    } catch (err) {
      toast.error(errorText(err));
      throw err;
    }
  }

  async function overwriteView() {
    if (!activeView) return;
    try {
      await updateView(activeView.id, viewPayload());
      await mutateGlobal(viewsKey());
      toast.success(`Вид «${activeView.name}» обновлён`);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  const group = state.filters.group ? groupsById.get(state.filters.group) : undefined;
  const title = activeView ? activeView.name : group ? group.name : 'Все контакты';
  const isFiltered = Boolean(state.q || activeFilterCount(state));
  const count = total?.count ?? contacts?.length ?? 0;

  return (
    <Page wide>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3 animate-fade-up">
        <div>
          <h1 className="font-display text-title">{title}</h1>
          <p className="mt-1 text-[13px] text-muted tabular">
            {count} {plural(count, 'контакт', 'контакта', 'контактов')}
          </p>
        </div>
        <Button variant="primary" onClick={() => newContact(state.q)}>
          <Plus /> Добавить контакт
        </Button>
      </header>

      <ContactsToolbar
        state={state}
        views={views}
        activeView={activeView}
        groups={groups}
        tags={tags}
        searchText={searchText}
        onSearchText={setSearchText}
        onFilter={setFilter}
        onClearFilters={() => go({ ...state, filters: {} })}
        onSort={(sort) => go({ ...state, sort })}
        onColumns={(cols) => go({ ...state, columns: cols })}
        onSelectView={(id) => router.push(id ? `${pathname}?view=${id}` : pathname)}
        onNewView={() => setIsViewDialogOpen(true)}
        onUpdateView={overwriteView}
      />

      <ContactsTable
        contacts={contacts}
        isLoading={isLoading}
        columns={columns}
        groupsById={groupsById}
        selected={selected}
        onToggle={toggle}
        onToggleAll={toggleAll}
        onUpdate={handleUpdate}
      />

      {contacts && contacts.length === 0 && (
        <div className="mt-6">
          {isFiltered ? (
            <EmptyState icon={SearchX} title="Ничего не нашлось">
              Попробуйте другой запрос или сбросьте фильтры.
            </EmptyState>
          ) : (
            <EmptyState icon={UserPlus} title="Контактов пока нет">
              Подключите Outlook или Google в «Синхронизации», загрузите файл в «Импорте» или нажмите «Добавить контакт».
            </EmptyState>
          )}
        </div>
      )}

      {hasMore && (
        <div className="mt-4 flex justify-center">
          <Button variant="outline" onClick={() => setSize(size + 1)} disabled={isValidating}>
            {isValidating ? 'Загружаю…' : 'Показать ещё'}
          </Button>
        </div>
      )}

      {selected.size > 0 && (
        <BulkBar
          count={selected.size}
          groups={groups}
          tags={tags}
          isBusy={isBusy}
          onClear={() => setSelected(new Set())}
          onAddTag={(tag) => runBulk('Тег добавлен', (c) => (c.tags.some((t) => t.toLowerCase() === tag.toLowerCase()) ? null : { tags: [...c.tags, tag] }))}
          onAddGroup={(gid) => runBulk('Добавлено в группу', (c) => (c.group_ids.includes(gid) ? null : { group_ids: [...c.group_ids, gid] }))}
          onFrequency={(days) => runBulk('Частота задана', (c) => ({ keep_in_touch: { frequency_days: days, snoozed_until: c.keep_in_touch.snoozed_until } }))}
          onPriority={(level) => runBulk('Приоритет задан', () => ({ priority: level }))}
          onDelete={bulkDelete}
        />
      )}

      <SaveViewDialog open={isViewDialogOpen} onOpenChange={setIsViewDialogOpen} onSave={saveView} />
    </Page>
  );
}
