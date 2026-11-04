'use client';

import { useMemo, useState, type ButtonHTMLAttributes } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { BellPlus, History, Plus } from 'lucide-react';
import type { Contact, ContactUpdate } from '@/lib/api';
import {
  createInteraction,
  deleteInteraction,
  getInteractions,
  interactionsKey,
  snoozeContact,
  updateInteraction,
  type Interaction,
  type InteractionKind,
  type InteractionPage,
} from '@/lib/api-crm';
import { cn, errorText } from '@/lib/utils';
import { EmptyState, Skeleton } from '@/components/app/page';
import { EditableText } from '@/components/contact/editable';
import { TimelineComposer, type ComposerValue } from '@/components/contact/timeline-composer';
import { TimelineItem } from '@/components/contact/timeline-item';
import { KIND_META, KIND_ORDER, monthTitle } from '@/components/contact/timeline-kinds';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/overlays';
import { SectionLabel } from '@/components/ui/section-label';

const PAGE_SIZE = 30;
const REMIND_DAYS = [7, 14, 30, 90] as const;

type Props = {
  contact: Contact;
  onSave: (patch: ContactUpdate) => void;
  onRefresh: () => void;
};

function groupByMonth(items: Interaction[]): { month: string; items: Interaction[] }[] {
  const groups: { month: string; items: Interaction[] }[] = [];
  for (const item of items) {
    const month = monthTitle(item.occurred_at);
    const last = groups[groups.length - 1];
    if (last?.month === month) last.items.push(item);
    else groups.push({ month, items: [item] });
  }
  return groups;
}

export function TimelineTab({ contact, onSave, onRefresh }: Props) {
  const { mutate: mutateGlobal } = useSWRConfig();
  const [kind, setKind] = useState<InteractionKind | null>(null);
  const [isComposing, setIsComposing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  // Страницы после первой: сбрасываются при смене фильтра и после любого изменения
  const [more, setMore] = useState<{ scope: string; items: Interaction[]; cursor: string | null } | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  const params = { contact_id: contact.id, include_events: true, limit: PAGE_SIZE, ...(kind ? { kind } : {}) };
  const key = interactionsKey(params);
  const { data: page, error, isLoading, mutate } = useSWR<InteractionPage>(key);

  const extra = more?.scope === key ? more : null;
  const items = useMemo(() => [...(page?.items ?? []), ...(extra?.items ?? [])], [page, extra]);
  const cursor = extra ? extra.cursor : (page?.next_cursor ?? null);
  const groups = useMemo(() => groupByMonth(items), [items]);

  async function refresh() {
    setMore(null);
    await mutate();
    void mutateGlobal((k) => typeof k === 'string' && (k.startsWith('/api/home') || k.startsWith('/api/interactions')));
    onRefresh();
  }

  async function loadMore() {
    if (!cursor) return;
    setIsLoadingMore(true);
    try {
      const next = await getInteractions({ ...params, cursor });
      setMore({ scope: key, items: [...(extra?.items ?? []), ...next.items], cursor: next.next_cursor });
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsLoadingMore(false);
    }
  }

  async function handleCreate(value: ComposerValue) {
    try {
      await createInteraction({ contact_ids: [contact.id], source: 'manual', ...value });
      setIsComposing(false);
      await refresh();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleUpdate(id: string, value: ComposerValue) {
    try {
      await updateInteraction(id, value);
      setEditingId(null);
      await refresh();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleDelete(item: Interaction) {
    const previous = page;
    // Оптимистично убираем запись; при ошибке возвращаем
    setMore((m) => (m ? { ...m, items: m.items.filter((i) => i.id !== item.id) } : m));
    void mutate(previous && { ...previous, items: previous.items.filter((i) => i.id !== item.id) }, { revalidate: false });
    try {
      await deleteInteraction(item.id);
      toast.success('Запись удалена');
      void mutateGlobal((k) => typeof k === 'string' && k.startsWith('/api/home'));
      onRefresh();
    } catch (err) {
      toast.error(errorText(err));
      await refresh();
    }
  }

  async function remind(days: number) {
    try {
      await snoozeContact(contact.id, days);
      toast.success(`Напомню через ${days} дн.`);
      onRefresh();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <div className="pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Фильтр по типу" className="flex flex-1 flex-wrap items-center gap-1">
          <FilterChip isActive={kind === null} onClick={() => setKind(null)}>
            Все
          </FilterChip>
          {KIND_ORDER.map((k) => (
            <FilterChip key={k} isActive={kind === k} onClick={() => setKind(kind === k ? null : k)}>
              {KIND_META[k].label}
            </FilterChip>
          ))}
        </div>
        <Menu>
          <MenuTrigger asChild>
            <Button variant="outline">
              <BellPlus /> Напомнить
            </Button>
          </MenuTrigger>
          <MenuContent align="end">
            <MenuLabel>Напомнить о контакте через</MenuLabel>
            {REMIND_DAYS.map((d) => (
              <MenuItem key={d} onSelect={() => void remind(d)}>
                {d} дн.
              </MenuItem>
            ))}
          </MenuContent>
        </Menu>
        <Button variant="primary" onClick={() => setIsComposing(true)} disabled={isComposing}>
          <Plus /> Добавить заметку
        </Button>
      </div>

      {isComposing && (
        <div className="mt-4">
          <TimelineComposer submitLabel="Сохранить" onSubmit={handleCreate} onCancel={() => setIsComposing(false)} />
        </div>
      )}

      <div className="mt-4">
        {isLoading && (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-14" />
            ))}
          </div>
        )}
        {error && <p className="py-6 text-center text-sm text-danger">Не удалось загрузить историю. {errorText(error)}</p>}
        {!isLoading && !error && items.length === 0 && (
          <EmptyState icon={History} title={kind ? 'Нет записей этого типа' : 'Пока нет записей'}>
            Записывайте звонки, встречи и важные детали — здесь соберётся вся история общения.
          </EmptyState>
        )}
        {groups.map((group) => (
          <section key={group.month} aria-label={group.month} className="mb-2">
            <SectionLabel className="sticky top-11 z-[1] block bg-bg/90 py-2 backdrop-blur">{group.month}</SectionLabel>
            <ul className="divide-y divide-line">
              {group.items.map((item) =>
                editingId === item.id ? (
                  <li key={item.id} className="py-3">
                    <TimelineComposer
                      initial={item}
                      submitLabel="Сохранить"
                      onSubmit={(v) => handleUpdate(item.id, v)}
                      onCancel={() => setEditingId(null)}
                    />
                  </li>
                ) : (
                  <TimelineItem key={item.id} item={item} onEdit={() => setEditingId(item.id)} onDelete={() => void handleDelete(item)} />
                ),
              )}
            </ul>
          </section>
        ))}
        {cursor && (
          <div className="flex justify-center py-4">
            <Button variant="outline" onClick={() => void loadMore()} disabled={isLoadingMore}>
              {isLoadingMore ? 'Загружаю…' : 'Показать ещё'}
            </Button>
          </div>
        )}
      </div>

      {contact.notes.trim() && (
        <section className="mt-8 border-t border-line pt-4">
          <SectionLabel className="mb-1.5 block">Заметки (старые)</SectionLabel>
          <EditableText
            isMultiline
            value={contact.notes}
            onCommit={(v) => onSave({ notes: v })}
            ariaLabel="Старые заметки"
            className="-mx-2 min-h-16"
          />
        </section>
      )}
    </div>
  );
}

function FilterChip({ isActive, className, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { isActive: boolean }) {
  return (
    <button
      type="button"
      aria-pressed={isActive}
      className={cn(
        'h-7 rounded-full px-2.5 text-[13px] transition-colors',
        isActive ? 'bg-fg text-bg' : 'text-muted hover:bg-hover hover:text-fg',
        className,
      )}
      {...props}
    />
  );
}
