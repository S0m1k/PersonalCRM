'use client';

/**
 * Поиск в одну строку (Ctrl+K): люди по имени/компании/почте/телефону + быстрые переходы.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Command } from 'cmdk';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import useSWR from 'swr';
import { CircleHelp, FileUp, Home, LayoutTemplate, Plus, RefreshCw, Search, Users } from 'lucide-react';
import type { Contact } from '@/lib/api';
import { fullName } from '@/lib/utils';
import { Avatar } from './avatar';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreateContact: (name: string) => void;
};

const itemClass =
  'flex h-9 cursor-default select-none items-center gap-2.5 rounded px-2 text-sm aria-selected:bg-hover [&_svg]:size-4 [&_svg]:text-muted';
const groupClass =
  '[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-faint';

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

export function CommandPalette({ open, onOpenChange, onCreateContact }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const q = useDebounced(query.trim(), 150);
  const { data: people = [], isLoading } = useSWR<Contact[]>(
    open && q ? `/api/contacts/?q=${encodeURIComponent(q)}&limit=8` : null,
    { keepPreviousData: true },
  );

  useEffect(() => {
    if (!open) setQuery('');
  }, [open]);

  function go(href: string) {
    onOpenChange(false);
    router.push(href);
  }

  const pages = [
    { label: 'Главная', href: '/', icon: Home },
    { label: 'Контакты', href: '/contacts', icon: Users },
    { label: 'Вопросы', href: '/questions', icon: CircleHelp },
    { label: 'Синхронизация', href: '/sync', icon: RefreshCw },
    { label: 'Импорт файла', href: '/import', icon: FileUp },
    { label: 'Шаблоны карточек', href: '/settings/templates', icon: LayoutTemplate },
  ];
  const matchingPages = pages.filter((page) => !q || page.label.toLowerCase().includes(q.toLowerCase()));

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-[rgb(15_15_15/0.4)] data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[14vh] z-50 w-[calc(100vw-32px)] max-w-xl -translate-x-1/2 overflow-hidden rounded-lg bg-surface shadow-pop data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-[0.98]"
        >
          <DialogPrimitive.Title className="sr-only">Поиск</DialogPrimitive.Title>
          <Command shouldFilter={false} loop>
            <div className="flex items-center gap-2 border-b border-line px-4">
              <Search className="size-[18px] shrink-0 text-faint" />
              <Command.Input
                value={query}
                onValueChange={setQuery}
                placeholder="Найти человека или раздел…"
                className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-faint focus-visible:ring-0"
              />
            </div>
            <Command.List className="max-h-[min(60vh,420px)] overflow-y-auto p-1.5">
              {q && people.length > 0 && (
                <Command.Group heading="Люди" className={groupClass}>
                  {people.map((p) => {
                    const name = fullName(p) || 'Без имени';
                    const sub = [p.position, p.company].filter(Boolean).join(', ');
                    return (
                      <Command.Item key={p.id} value={`contact-${p.id}`} onSelect={() => go(`/contacts/${p.id}`)} className={itemClass}>
                        <Avatar name={name} size="sm" />
                        <span className="truncate">{name}</span>
                        {sub && <span className="truncate text-xs text-faint">{sub}</span>}
                      </Command.Item>
                    );
                  })}
                </Command.Group>
              )}
              {q && !isLoading && people.length === 0 && (
                <div className="px-2 py-3 text-sm text-muted">Никого не нашлось по «{q}»</div>
              )}
              {q && (
                <Command.Group heading="Действия" className={groupClass}>
                  <Command.Item
                    value="create"
                    onSelect={() => {
                      onOpenChange(false);
                      onCreateContact(query.trim());
                    }}
                    className={itemClass}
                  >
                    <Plus />
                    Новый контакт «{query.trim()}»
                  </Command.Item>
                </Command.Group>
              )}
              {matchingPages.length > 0 && (
                <Command.Group heading="Перейти" className={groupClass}>
                  {matchingPages.map(({ label, href, icon: Icon }) => (
                    <Command.Item key={href} value={`page-${href}`} onSelect={() => go(href)} className={itemClass}>
                      <Icon />
                      {label}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
