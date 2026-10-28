'use client';

import { useState } from 'react';
import { CircleCheck, Trash2 } from 'lucide-react';
import type { ApplyResult, CaptureResult } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';

type Props = {
  result: CaptureResult;
  applied: ApplyResult | null;
  busy: boolean;
  onApply: (actions: number[], contactId: string | null) => void;
  onDiscard: () => void;
};

/** «Удали контакт Иван Петров»: какую карточку нашли — и удалить только после подтверждения. */
export function DeletePreview({ result, applied, busy, onApply, onDiscard }: Props) {
  const [target, setTarget] = useState<string>(result.contact_id ?? '');
  const chosen = result.candidates.find((c) => c.id === target);

  if (applied?.deleted_contact) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-line bg-surface px-4 py-3 text-sm">
        <CircleCheck className="size-4 text-accent" />
        Контакт «{applied.deleted_contact.name}» удалён: он в корзине, его вопросы удалены, встречи отвязаны.
      </div>
    );
  }

  if (result.candidates.length === 0) {
    return (
      <div className="flex flex-wrap items-center gap-2.5 rounded-md border border-line bg-surface px-3 py-2.5 text-sm">
        <Trash2 className="size-4 shrink-0 text-muted" />
        <span className="flex-1 text-muted">
          Не нашёл контакт{result.target_name ? ` «${result.target_name}»` : ''} — ничего не удалено. Проверьте имя в
          списке контактов.
        </span>
        <Button size="sm" variant="ghost" onClick={onDiscard}>
          Закрыть
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <fieldset>
        <legend className="mb-1.5 text-sm font-semibold text-muted">
          {result.candidates.length > 1 ? 'Какой контакт удалить?' : 'Удалить контакт?'}
        </legend>
        <div className="flex flex-wrap gap-1.5">
          {result.candidates.map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={target === c.id}
              onClick={() => setTarget(c.id)}
              className={cn(
                'inline-flex h-7 items-center gap-1 rounded-full border px-3 text-sm transition-colors',
                target === c.id
                  ? 'border-danger bg-danger text-white [&_.text-faint]:text-white/70'
                  : 'border-line text-muted hover:bg-hover hover:text-fg',
              )}
            >
              {c.name}
              {(c.company || c.city) && <span className="text-faint"> · {c.company || c.city}</span>}
            </button>
          ))}
        </div>
        <p className="mt-2 text-sm text-muted">
          Контакт уйдёт в корзину: его вопросы удалятся, встречи отвяжутся. В интерфейсе восстановить его пока нельзя.
        </p>
      </fieldset>

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          className="bg-danger hover:bg-danger/90"
          disabled={!chosen || busy}
          onClick={() => onApply([0], target)}
        >
          <Trash2 /> Удалить{chosen ? ` «${chosen.name}»` : ''}
        </Button>
        <Button variant="ghost" onClick={onDiscard} disabled={busy}>
          Отмена
        </Button>
      </div>
    </div>
  );
}
