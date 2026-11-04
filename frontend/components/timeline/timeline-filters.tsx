'use client';

import { useEffect, useState } from 'react';
import { Filter, Search, SlidersHorizontal } from 'lucide-react';
import type { InteractionKind } from '@/lib/api-crm';
import { cn } from '@/lib/utils';
import { ContactPicker, type PickedContact } from '@/components/calendar/contact-picker';
import { INTERACTION_KINDS, INTERACTION_KIND_ORDER } from '@/components/interactions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';
import { SectionLabel } from '@/components/ui/section-label';

const SEARCH_DEBOUNCE_MS = 300;

interface FiltersProps {
  kinds: InteractionKind[];
  contacts: PickedContact[];
  from: string;
  to: string;
  onKinds: (kinds: InteractionKind[]) => void;
  onContacts: (contacts: PickedContact[]) => void;
  onRange: (from: string, to: string) => void;
  activeCount: number;
}

/** Поповер «Фильтры»: типы (мультивыбор), люди, период. */
export function FilterPopover({ kinds, contacts, from, to, onKinds, onContacts, onRange, activeCount }: FiltersProps) {
  function toggle(kind: InteractionKind) {
    onKinds(kinds.includes(kind) ? kinds.filter((k) => k !== kind) : [...kinds, kind]);
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" aria-label="Фильтры">
          <Filter /> Фильтры{activeCount > 0 && <span className="rounded-full bg-accent px-1.5 text-[11px] text-accent-fg">{activeCount}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-4 p-4">
        <div className="space-y-1.5">
          <SectionLabel>Тип</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {INTERACTION_KIND_ORDER.map((k) => {
              const isOn = kinds.includes(k);
              const { icon: Icon, label } = INTERACTION_KINDS[k];
              return (
                <button
                  key={k}
                  type="button"
                  aria-pressed={isOn}
                  onClick={() => toggle(k)}
                  className={cn(
                    'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[13px] [&_svg]:size-3.5',
                    isOn ? 'border-accent-300 bg-accent-50 text-accent-700 dark:border-accent-700 dark:bg-accent-950 dark:text-accent-200' : 'border-line text-muted hover:bg-hover',
                  )}
                >
                  <Icon aria-hidden /> {label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="space-y-1.5">
          <SectionLabel>Люди</SectionLabel>
          <ContactPicker value={contacts} onChange={onContacts} />
        </div>
        <div className="space-y-1.5">
          <SectionLabel>Период</SectionLabel>
          <div className="flex items-center gap-2">
            <Input type="date" aria-label="С даты" value={from} max={to || undefined} onChange={(e) => onRange(e.target.value, to)} />
            <span className="text-muted">—</span>
            <Input type="date" aria-label="По дату" value={to} min={from || undefined} onChange={(e) => onRange(from, e.target.value)} />
          </div>
        </div>
        {activeCount > 0 && (
          <Button variant="ghost" size="sm" onClick={() => { onKinds([]); onContacts([]); onRange('', ''); }}>
            Сбросить фильтры
          </Button>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Поповер «Отображение»: события календаря в ленте. */
export function DisplayPopover({ includeEvents, onChange }: { includeEvents: boolean; onChange: (v: boolean) => void }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" aria-label="Настройки отображения">
          <SlidersHorizontal />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="p-3">
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-accent" checked={includeEvents} onChange={(e) => onChange(e.target.checked)} />
          Показывать события календаря
        </label>
      </PopoverContent>
    </Popover>
  );
}

/** Поле поиска с задержкой; value — то, что сейчас в URL. */
export function SearchBox({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [text, setText] = useState(value);
  useEffect(() => {
    if (text === value) return;
    const id = setTimeout(() => onCommit(text.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [text, value, onCommit]);
  return (
    <div className="relative">
      <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
      <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Поиск по записям" aria-label="Поиск по записям" className="h-8 w-48 pl-8" />
    </div>
  );
}
