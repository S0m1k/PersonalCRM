'use client';

import { useState, type FormEvent } from 'react';
import type { Interaction, InteractionKind } from '@/lib/api-crm';
import { cn } from '@/lib/utils';
import { KIND_META, KIND_ORDER, toLocalInput } from '@/components/contact/timeline-kinds';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';

export type ComposerValue = {
  kind: InteractionKind;
  title: string;
  body: string;
  /** ISO */
  occurred_at: string;
};

type Props = {
  initial?: Interaction;
  submitLabel: string;
  onSubmit: (value: ComposerValue) => Promise<void> | void;
  onCancel: () => void;
};

/** Форма записи в Timeline: тип, заголовок, текст, дата. Одна и та же для добавления и правки. */
export function TimelineComposer({ initial, submitLabel, onSubmit, onCancel }: Props) {
  const [kind, setKind] = useState<InteractionKind>(initial?.kind ?? 'note');
  const [title, setTitle] = useState(initial?.title ?? '');
  const [body, setBody] = useState(initial?.body ?? '');
  const [when, setWhen] = useState(() => toLocalInput(initial?.occurred_at ?? new Date()));
  const [isBusy, setIsBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!title.trim() && !body.trim()) return;
    setIsBusy(true);
    try {
      await onSubmit({
        kind,
        title: title.trim(),
        body: body.trim(),
        occurred_at: when ? new Date(when).toISOString() : new Date().toISOString(),
      });
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-xs">
      <div role="radiogroup" aria-label="Тип записи" className="flex flex-wrap gap-1.5">
        {KIND_ORDER.map((k) => {
          const { icon: Icon, label, tone } = KIND_META[k];
          const isSelected = k === kind;
          return (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => setKind(k)}
              className={cn(
                'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[13px] transition-colors [&_svg]:size-3.5',
                isSelected ? `border-transparent ${tone}` : 'border-line text-muted hover:bg-hover hover:text-fg',
              )}
            >
              <Icon /> {label}
            </button>
          );
        })}
      </div>
      <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Заголовок (необязательно)" aria-label="Заголовок" maxLength={200} />
      <Textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="О чём говорили, договорённости, детали…"
        aria-label="Текст записи"
        autoFocus
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Input
          type="datetime-local"
          value={when}
          onChange={(e) => setWhen(e.target.value)}
          aria-label="Дата и время"
          className="w-auto"
        />
        <div className="flex gap-2">
          <Button type="button" variant="ghost" onClick={onCancel}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={isBusy || (!title.trim() && !body.trim())}>
            {submitLabel}
          </Button>
        </div>
      </div>
    </form>
  );
}
