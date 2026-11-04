'use client';

import { useState, type FormEvent } from 'react';
import useSWR from 'swr';
import { ExternalLink } from 'lucide-react';
import type { Contact } from '@/lib/api';
import { goalsKey, type GoalsState } from '@/lib/api-goals';
import { cn } from '@/lib/utils';
import { ChipInput } from '@/components/contact/chip-input';
import { SOCIAL_KEYS, SOCIAL_META, socialHref, type SocialKey } from '@/components/contact/social';
import type { SaveContact } from '@/components/contact/types';
import { Card, CardHeader } from '@/components/ui/card';

type CardProps = { contact: Contact; onSave: SaveContact };

/** Сферы «Колеса баланса» по умолчанию — те же, что у стратегии на сервере (models/goals.py) */
const DEFAULT_LIFE_AREAS = ['Семья', 'Друзья', 'Работа и карьера', 'Здоровье', 'Развитие', 'Хобби и отдых', 'Сообщество'];
const SCALE = [1, 2, 3, 4, 5] as const;

function SocialRow({ contact, field, isFocused, onSave }: CardProps & { field: SocialKey; isFocused: boolean }) {
  const meta = SOCIAL_META[field];
  const Icon = meta.icon;
  const saved = contact.social[field];
  const [draft, setDraft] = useState(saved);
  const [syncedFrom, setSyncedFrom] = useState(saved);
  const [error, setError] = useState<string | null>(null);
  const href = socialHref(field, saved);

  // Значение пришло с сервера (откат или обновление) — показываем его
  if (saved !== syncedFrom) {
    setSyncedFrom(saved);
    setDraft(saved);
  }

  async function commit(e?: FormEvent) {
    e?.preventDefault();
    const value = draft.trim();
    if (value === saved) {
      setError(null);
      return;
    }
    const message = await onSave({ social: { ...contact.social, [field]: value } }, { silent: true });
    setError(message);
  }

  return (
    <form onSubmit={(e) => void commit(e)} className="py-1">
      <div className="flex items-center gap-2">
        <Icon className="size-4 shrink-0 text-faint" aria-hidden />
        <input
          id={`social-${field}`}
          autoFocus={isFocused}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => void commit()}
          placeholder={`${meta.label}: ${meta.placeholder}`}
          aria-label={meta.label}
          aria-invalid={error ? true : undefined}
          className={cn(
            'h-8 min-w-0 flex-1 rounded-lg border bg-transparent px-2 text-sm outline-none placeholder:text-faint focus:ring-[3px]',
            error ? 'border-danger focus:ring-danger/20' : 'border-transparent hover:bg-hover focus:border-accent focus:bg-surface focus:ring-accent/20',
          )}
        />
        {href && (
          <a href={href} target="_blank" rel="noopener noreferrer" aria-label={`Открыть ${meta.label}`} className="text-faint hover:text-fg">
            <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
      {error && (
        <p role="alert" className="mt-1 pl-6 text-xs text-danger">
          {error}
        </p>
      )}
    </form>
  );
}

export function SocialCard({ contact, onSave, focusKey }: CardProps & { focusKey?: string }) {
  return (
    <Card>
      <CardHeader label="Соцсети" />
      {SOCIAL_KEYS.map((field) => (
        <SocialRow key={field} contact={contact} field={field} isFocused={focusKey === field} onSave={onSave} />
      ))}
    </Card>
  );
}

export function LifeAreasCard({ contact, onSave }: CardProps) {
  // Подсказки — из настроек «Колеса баланса» пользователя, чтобы сферы совпадали со стратегией
  const { data: goals } = useSWR<GoalsState>(goalsKey());
  const spheres = goals?.settings.life_balance.spheres.map((s) => s.name);
  const suggestions = spheres?.length ? spheres : DEFAULT_LIFE_AREAS;
  return (
    <Card>
      <CardHeader label="Сферы жизни" />
      <ChipInput
        values={contact.life_areas}
        onChange={(life_areas) => void onSave({ life_areas })}
        suggestions={suggestions}
        placeholder="Добавить сферу…"
        ariaLabel="Новая сфера жизни"
        emptyText="Сферы «Колеса баланса», к которым относится человек."
      />
    </Card>
  );
}

function Scale({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-muted" id={`scale-${label}`}>
        {label}
      </span>
      <div role="radiogroup" aria-labelledby={`scale-${label}`} className="inline-flex overflow-hidden rounded-lg border border-line">
        {SCALE.map((n) => {
          const isSelected = value === n;
          return (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => onChange(isSelected ? null : n)}
              className={cn(
                'h-8 w-9 text-sm font-medium transition-colors border-l border-line first:border-l-0',
                isSelected ? 'bg-accent text-accent-fg' : 'text-muted hover:bg-hover hover:text-fg',
              )}
            >
              {n}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ScoresCard({ contact, onSave }: CardProps) {
  return (
    <Card>
      <CardHeader label="Важность и близость" />
      <div className="flex flex-col gap-3">
        <Scale label="Важность" value={contact.importance} onChange={(importance) => void onSave({ importance })} />
        <Scale label="Близость" value={contact.closeness} onChange={(closeness) => void onSave({ closeness })} />
      </div>
      <p className="mt-3 text-xs text-faint">От 1 до 5. Нажмите на выбранное значение, чтобы сбросить. Используется в Priority Map.</p>
    </Card>
  );
}
