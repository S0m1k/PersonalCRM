'use client';

import { useState, type FormEvent } from 'react';
import { Plus, X } from 'lucide-react';
import { cn } from '@/lib/utils';

type Item = { value: string; label: string };

type Props = {
  items: Item[];
  kind: 'tel' | 'email';
  defaultLabel: string;
  onChange: (items: Item[]) => void;
};

/** Список значений с подписями (телефоны, почта): ссылка, удаление по наведению, добавление снизу. */
export function MultiValue({ items, kind, defaultLabel, onChange }: Props) {
  const [isAdding, setIsAdding] = useState(false);
  const [draft, setDraft] = useState('');

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    const value = draft.trim();
    setIsAdding(false);
    setDraft('');
    if (value) onChange([...items, { value, label: defaultLabel }]);
  }

  const href = (value: string) => (kind === 'tel' ? `tel:${value.replace(/[^\d+]/g, '')}` : `mailto:${value}`);

  return (
    <div className="flex flex-col">
      {items.map((item, index) => (
        <div key={`${item.value}-${index}`} className="group flex min-h-8 flex-wrap items-center gap-x-2 rounded px-2 hover:bg-hover">
          <a href={href(item.value)} className={cn('text-sm underline decoration-line underline-offset-4 hover:decoration-fg', kind === 'tel' ? 'shrink-0 whitespace-nowrap' : 'min-w-0 max-w-full truncate')}
            title={item.value}>
            {item.value}
          </a>
          <span className="min-w-0 truncate text-xs text-faint" title={item.label}>{item.label}</span>
          <button
            type="button"
            onClick={() => onChange(items.filter((_, i) => i !== index))}
            className="ml-auto rounded p-0.5 text-faint opacity-0 hover:bg-line hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
            aria-label={`Удалить ${item.value}`}
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
      {isAdding ? (
        <form onSubmit={handleAdd}>
          <input
            autoFocus
            type={kind}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={handleAdd}
            onKeyDown={(e) => e.key === 'Escape' && setIsAdding(false)}
            placeholder={kind === 'tel' ? '+7 900 000-00-00' : 'name@example.com'}
            className="h-8 w-full rounded bg-surface px-2 text-sm shadow-pop outline-none"
          />
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setIsAdding(true)}
          className="flex h-8 items-center gap-1.5 rounded px-2 text-sm text-faint hover:bg-hover hover:text-muted"
        >
          {items.length ? <Plus className="size-3.5" /> : null}
          {items.length ? 'Добавить' : 'Пусто'}
        </button>
      )}
    </div>
  );
}
