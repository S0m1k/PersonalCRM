'use client';

import { useState, type ReactNode } from 'react';
import { ArrowDownUp, Check, ChevronDown, Columns3, ListFilter, Plus, Search, X } from 'lucide-react';
import type { Group, TagCount } from '@/lib/api-crm';
import type { ContactView } from '@/lib/api-views';
import { COLUMNS, DEFAULT_COLUMNS, SORTS, activeFilterCount, type ColumnId, type FilterKey, type ListState } from '@/lib/contact-view';
import { PRIORITY_LEVELS, PRIORITY_META } from '@/lib/priority';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger, Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';

const SOURCES = [
  { id: 'manual', label: 'Вручную' },
  { id: 'google', label: 'Google' },
  { id: 'outlook', label: 'Outlook' },
  { id: 'csv', label: 'CSV' },
  { id: 'vcard', label: 'vCard' },
  { id: 'telegram', label: 'Telegram' },
];

const selectClass =
  'h-8 w-full rounded-lg border border-line-strong bg-surface px-2 text-sm text-fg focus-visible:border-accent focus-visible:outline-none';

type Props = {
  state: ListState;
  views: ContactView[];
  activeView: ContactView | undefined;
  groups: Group[];
  tags: TagCount[];
  searchText: string;
  onSearchText: (value: string) => void;
  onFilter: (key: FilterKey, value: string) => void;
  onClearFilters: () => void;
  onSort: (sort: ListState['sort']) => void;
  onColumns: (columns: ColumnId[]) => void;
  onSelectView: (id: string | null) => void;
  onNewView: () => void;
  onUpdateView: () => void;
};

export function ContactsToolbar(props: Props) {
  const { state, views, activeView, searchText, onSearchText } = props;
  const columns = (state.columns ?? DEFAULT_COLUMNS) as ColumnId[];
  const filterCount = activeFilterCount(state);

  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5">
      <Menu>
        <MenuTrigger asChild>
          <Button variant="outline" size="sm" aria-label="Выбрать вид">
            <span aria-hidden>{activeView?.emoji}</span>
            {activeView ? activeView.name : 'Все контакты'}
            <ChevronDown className="!size-3.5 text-faint" />
          </Button>
        </MenuTrigger>
        <MenuContent align="start" className="min-w-56">
          <MenuItem onSelect={() => props.onSelectView(null)}>
            <Check className={cn(activeView && 'invisible')} /> Все контакты
          </MenuItem>
          {views.map((v) => (
            <MenuItem key={v.id} onSelect={() => props.onSelectView(v.id)}>
              <Check className={cn(activeView?.id !== v.id && 'invisible')} />
              {v.emoji} {v.name}
            </MenuItem>
          ))}
          <MenuSeparator />
          {activeView && (
            <MenuItem onSelect={props.onUpdateView}>
              <Check /> Обновить «{activeView.name}»
            </MenuItem>
          )}
          <MenuItem onSelect={props.onNewView}>
            <Plus /> Новый вид
          </MenuItem>
        </MenuContent>
      </Menu>
      <Button variant="ghost" size="sm" onClick={props.onNewView} aria-label="Сохранить текущие фильтры как вид" title="Новый вид">
        <Plus />
      </Button>

      <div className="ml-auto flex flex-wrap items-center gap-1.5">
        <FilterPopover {...props} count={filterCount} />
        <SortMenu sort={state.sort} onSort={props.onSort} />
        <ColumnsMenu columns={columns} onColumns={props.onColumns} />
        <label className="relative flex h-8 w-44 items-center sm:w-56">
          <Search className="pointer-events-none absolute left-2.5 size-4 text-faint" aria-hidden />
          <input
            value={searchText}
            onChange={(e) => onSearchText(e.target.value)}
            placeholder="Поиск"
            aria-label="Поиск по контактам"
            className="h-full w-full rounded-lg bg-transparent pl-8 pr-2 text-sm outline-none placeholder:text-faint hover:bg-hover focus-visible:bg-hover"
          />
        </label>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block px-2 py-1">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
    </label>
  );
}

function FilterPopover({ state, groups, tags, count, onFilter, onClearFilters }: Props & { count: number }) {
  const f = state.filters;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className={cn(count > 0 && 'bg-accent/10 text-accent hover:bg-accent/15 hover:text-accent')}>
          <ListFilter /> Фильтр{count > 0 && ` · ${count}`}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-2">
        <Field label="Тег">
          <select className={selectClass} value={f.tag ?? ''} onChange={(e) => onFilter('tag', e.target.value)}>
            <option value="">Любой</option>
            {tags.map((t) => (
              <option key={t.tag} value={t.tag}>{t.tag} ({t.count})</option>
            ))}
          </select>
        </Field>
        <Field label="Группа">
          <select className={selectClass} value={f.group ?? ''} onChange={(e) => onFilter('group', e.target.value)}>
            <option value="">Любая</option>
            {groups.map((g) => (
              <option key={g.id} value={g.id}>{g.emoji} {g.name}</option>
            ))}
          </select>
        </Field>
        <Field label="Приоритет">
          <select className={selectClass} value={f.priority ?? ''} onChange={(e) => onFilter('priority', e.target.value)}>
            <option value="">Любой</option>
            {PRIORITY_LEVELS.map((l) => (
              <option key={l} value={l}>{PRIORITY_META[l].label}</option>
            ))}
            <option value="unset">Не задан</option>
          </select>
        </Field>
        <Field label="Частота общения">
          <select className={selectClass} value={f.freq ?? ''} onChange={(e) => onFilter('freq', e.target.value)}>
            <option value="">Любая</option>
            <option value="set">Задана</option>
            <option value="unset">Не задана</option>
          </select>
        </Field>
        <Field label="Место">
          <select className={selectClass} value={f.loc ?? ''} onChange={(e) => onFilter('loc', e.target.value)}>
            <option value="">Не важно</option>
            <option value="1">Есть координаты</option>
            <option value="0">Нет координат</option>
          </select>
        </Field>
        <Field label="Источник">
          <select className={selectClass} value={f.src ?? ''} onChange={(e) => onFilter('src', e.target.value)}>
            <option value="">Любой</option>
            {SOURCES.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
        </Field>
        <Field label="Не общались дольше (дней)">
          <input
            type="number"
            min={1}
            max={3650}
            inputMode="numeric"
            value={f.inactive ?? ''}
            placeholder="Например, 90"
            onChange={(e) => onFilter('inactive', e.target.value)}
            className={selectClass}
          />
        </Field>
        {count > 0 && (
          <div className="mt-1 border-t border-line px-1 pt-2">
            <Button variant="ghost" size="sm" onClick={onClearFilters}>
              <X /> Сбросить фильтры
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

function SortMenu({ sort, onSort }: { sort: ListState['sort']; onSort: (s: ListState['sort']) => void }) {
  const current = SORTS.find((s) => s.id === sort);
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size="sm" className={cn(current && 'text-fg')}>
          <ArrowDownUp /> {current ? current.label : 'Сортировка'}
        </Button>
      </MenuTrigger>
      <MenuContent align="end">
        <MenuLabel>Сортировать</MenuLabel>
        {SORTS.map((s) => (
          <MenuItem key={s.id} onSelect={() => onSort(s.id)}>
            <Check className={cn(sort !== s.id && 'invisible')} /> {s.label}
          </MenuItem>
        ))}
        {sort && (
          <>
            <MenuSeparator />
            <MenuItem onSelect={() => onSort(null)}>
              <X /> По умолчанию
            </MenuItem>
          </>
        )}
      </MenuContent>
    </Menu>
  );
}

function ColumnsMenu({ columns, onColumns }: { columns: ColumnId[]; onColumns: (c: ColumnId[]) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  function toggle(id: ColumnId) {
    const next = COLUMNS.map((c) => c.id).filter((c) => (c === id ? !columns.includes(c) : columns.includes(c)));
    onColumns(next);
  }
  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          <Columns3 /> Колонки
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-60">
        {COLUMNS.map((c) => (
          <label key={c.id} className="flex h-8 cursor-pointer items-center gap-2 rounded-lg px-2 text-sm hover:bg-hover">
            <input type="checkbox" checked={columns.includes(c.id)} onChange={() => toggle(c.id)} className="size-4 accent-[rgb(var(--accent))]" />
            {c.label}
          </label>
        ))}
      </PopoverContent>
    </Popover>
  );
}
