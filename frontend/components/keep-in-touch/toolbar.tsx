'use client';

import { Check, Filter, SlidersHorizontal } from 'lucide-react';
import type { Group, TagCount } from '@/lib/api-crm';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger, Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';
import { KIT_COLUMNS, type KitDisplay } from './display';

export type KitView = 'board' | 'list' | 'upcoming';

const VIEWS: Array<{ id: KitView; label: string }> = [
  { id: 'board', label: 'Доска' },
  { id: 'list', label: 'Список' },
  { id: 'upcoming', label: 'Ближайшие' },
];

export function ViewSwitch({ value, onChange }: { value: KitView; onChange: (v: KitView) => void }) {
  return (
    <div role="radiogroup" aria-label="Вид" className="inline-flex rounded-lg border border-line bg-surface p-0.5">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          type="button"
          role="radio"
          aria-checked={value === v.id}
          onClick={() => onChange(v.id)}
          className={cn(
            'h-7 rounded-md px-3 text-[13px] font-medium transition-colors',
            value === v.id ? 'bg-olive-100 text-fg' : 'text-muted hover:text-fg',
          )}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

interface FilterProps {
  groups: Group[];
  tags: TagCount[];
  groupId: string;
  tag: string;
  onChange: (patch: { group: string; tag: string }) => void;
}

/** Дропдаун фильтра: все контакты / группа / тег. */
export function FilterMenu({ groups, tags, groupId, tag, onChange }: FilterProps) {
  const label = groupId ? (groups.find((g) => g.id === groupId)?.name ?? 'Группа') : tag ? `#${tag}` : 'Все контакты';
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="outline" size="sm" aria-label="Фильтр">
          <Filter /> {label}
        </Button>
      </MenuTrigger>
      <MenuContent align="start" className="max-h-80 overflow-y-auto">
        <MenuItem onSelect={() => onChange({ group: '', tag: '' })}>
          Все контакты {!groupId && !tag && <Check className="ml-auto" />}
        </MenuItem>
        {groups.length > 0 && <MenuSeparator />}
        {groups.length > 0 && <MenuLabel>Группы</MenuLabel>}
        {groups.map((g) => (
          <MenuItem key={g.id} onSelect={() => onChange({ group: g.id, tag: '' })}>
            {g.emoji} {g.name} {g.id === groupId && <Check className="ml-auto" />}
          </MenuItem>
        ))}
        {tags.length > 0 && <MenuSeparator />}
        {tags.length > 0 && <MenuLabel>Теги</MenuLabel>}
        {tags.map((t) => (
          <MenuItem key={t.tag} onSelect={() => onChange({ group: '', tag: t.tag })}>
            #{t.tag} {t.tag === tag && <Check className="ml-auto" />}
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

export function DisplayPopover({ display, onChange }: { display: KitDisplay; onChange: (patch: Partial<KitDisplay>) => void }) {
  function toggleColumn(id: string, isVisible: boolean) {
    onChange({ hiddenColumns: isVisible ? display.hiddenColumns.filter((c) => c !== id) : [...display.hiddenColumns, id] });
  }
  const row = 'flex cursor-pointer items-center gap-2 py-1 text-sm';
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" aria-label="Настройки отображения">
          <SlidersHorizontal /> Настройки отображения
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-64 p-3">
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Колонки доски</div>
        {KIT_COLUMNS.map((c) => {
          const isVisible = !display.hiddenColumns.includes(c.id);
          return (
            <label key={c.id} className={row}>
              <input type="checkbox" className="size-4 accent-accent" checked={isVisible} onChange={() => toggleColumn(c.id, isVisible)} />
              {c.label}
            </label>
          );
        })}
        <div className="my-2 h-px bg-line" />
        <label className={row}>
          <input type="checkbox" className="size-4 accent-accent" checked={display.showSnoozed} onChange={(e) => onChange({ showSnoozed: e.target.checked })} />
          Показывать отложенных
        </label>
        <label className={row}>
          <input type="checkbox" className="size-4 accent-accent" checked={display.compact} onChange={(e) => onChange({ compact: e.target.checked })} />
          Компактные карточки
        </label>
      </PopoverContent>
    </Popover>
  );
}
