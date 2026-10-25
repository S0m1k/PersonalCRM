'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { Plus, X } from 'lucide-react';
import type { Contact } from '@/lib/api';
import { fullName } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';

export type PickedContact = { id: string; name: string };

type Props = {
  value: PickedContact[];
  onChange: (value: PickedContact[]) => void;
};

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Люди на встрече: плашки выбранных + поиск по базе. */
export function ContactPicker({ value, onChange }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const q = useDebounced(query.trim(), 150);
  const { data: found = [] } = useSWR<Contact[]>(
    isOpen ? `/api/contacts/?limit=8${q ? `&q=${encodeURIComponent(q)}` : ''}` : null,
    { keepPreviousData: true },
  );
  const chosen = new Set(value.map((c) => c.id));

  function add(contact: Contact) {
    onChange([...value, { id: contact.id, name: fullName(contact) || 'Без имени' }]);
    setQuery('');
    setIsOpen(false);
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {value.map((c) => (
        <span key={c.id} className="flex h-7 items-center gap-1.5 rounded-full bg-hover pl-1 pr-1.5 text-sm">
          <Avatar name={c.name} size="sm" />
          {c.name}
          <button
            type="button"
            onClick={() => onChange(value.filter((v) => v.id !== c.id))}
            className="rounded-full p-0.5 text-faint hover:bg-line hover:text-fg"
            aria-label={`Убрать ${c.name}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          <Button type="button" variant="ghost" size="sm">
            <Plus /> Человек
          </Button>
        </PopoverTrigger>
        <PopoverContent className="p-2">
          <Input autoFocus placeholder="Имя, компания, почта…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <ul className="mt-1 max-h-60 overflow-y-auto">
            {found
              .filter((c) => !chosen.has(c.id))
              .map((c) => (
                <li key={c.id}>
                  <button
                    type="button"
                    onClick={() => add(c)}
                    className="flex h-8 w-full items-center gap-2 rounded px-1.5 text-left text-sm hover:bg-hover"
                  >
                    <Avatar name={fullName(c) || '?'} size="sm" />
                    <span className="flex-1 truncate">{fullName(c) || 'Без имени'}</span>
                    {c.company && <span className="truncate text-xs text-faint">{c.company}</span>}
                  </button>
                </li>
              ))}
            {found.length === 0 && <li className="px-1.5 py-2 text-sm text-faint">Никого не нашлось</li>}
          </ul>
        </PopoverContent>
      </Popover>
    </div>
  );
}
