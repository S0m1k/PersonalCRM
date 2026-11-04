'use client';

import { useState, type FormEvent } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Tag } from '@/components/ui/tag';

const MAX_LEN = 50;
const MAX_SUGGESTIONS = 6;

type Props = {
  values: string[];
  onChange: (values: string[]) => void;
  /** Подсказки для автодополнения */
  suggestions?: string[];
  placeholder: string;
  ariaLabel: string;
  emptyText?: string;
};

/** Список меток-чипов с удалением и полем добавления с автодополнением (теги, сферы жизни). */
export function ChipInput({ values, onChange, suggestions = [], placeholder, ariaLabel, emptyText }: Props) {
  const [draft, setDraft] = useState('');
  const taken = new Set(values.map((v) => v.toLowerCase()));
  const query = draft.trim().toLowerCase();
  const matches = suggestions
    .filter((s) => !taken.has(s.toLowerCase()) && (!query || s.toLowerCase().includes(query)))
    .slice(0, MAX_SUGGESTIONS);

  function add(raw: string) {
    const value = raw.trim().slice(0, MAX_LEN);
    setDraft('');
    if (value && !taken.has(value.toLowerCase())) onChange([...values, value]);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    add(draft);
  }

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {values.length === 0 && emptyText && <span className="text-sm text-faint">{emptyText}</span>}
        {values.map((value) => (
          <Tag key={value} className="pr-1">
            {value}
            <button
              type="button"
              onClick={() => onChange(values.filter((v) => v !== value))}
              className="rounded-full p-0.5 text-muted hover:bg-fg/10 hover:text-fg"
              aria-label={`Убрать «${value}»`}
            >
              <X className="size-3" />
            </button>
          </Tag>
        ))}
      </div>
      <form onSubmit={handleSubmit} className="mt-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={placeholder}
          aria-label={ariaLabel}
          maxLength={MAX_LEN}
          className={cn(
            'h-8 w-full rounded-lg border border-line bg-transparent px-2.5 text-sm outline-none placeholder:text-faint',
            'focus:border-accent focus:ring-[3px] focus:ring-accent/20',
          )}
        />
      </form>
      {matches.length > 0 && (
        <ul className="mt-1.5 flex flex-wrap gap-1" aria-label="Подсказки">
          {matches.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => add(s)}
                className="h-6 rounded-full border border-dashed border-line px-2 text-xs text-muted hover:bg-hover hover:text-fg"
              >
                + {s}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
