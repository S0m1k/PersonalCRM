'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { PRIORITY_LEVELS, PRIORITY_META, isPriorityLevel, priorityLabel } from '@/lib/priority';
import { FREQUENCY_PRESETS, frequencyLabel } from '@/lib/frequency';
import { Pill } from '@/components/ui/pill';
import { Tag } from '@/components/ui/tag';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';

const optionClass =
  'flex h-8 w-full items-center gap-2 rounded-lg px-2 text-left text-sm hover:bg-hover focus-visible:bg-hover focus-visible:outline-none';

/** Должность: текст, по клику превращается в поле; Enter/потеря фокуса сохраняют, Esc отменяет. */
export function EditableText({
  value,
  label,
  placeholder,
  onSave,
}: {
  value: string;
  label: string;
  placeholder: string;
  onSave: (next: string) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);

  if (draft === null) {
    return (
      <button
        type="button"
        aria-label={`${label}: ${value || 'не задано'}. Изменить`}
        onClick={(e) => {
          e.stopPropagation();
          setDraft(value);
        }}
        className="-mx-1 block max-w-full truncate rounded px-1 py-0.5 text-left hover:bg-hover"
      >
        {value || <span className="inline-flex items-center gap-1 text-faint"><Plus className="size-3" aria-hidden />{placeholder}</span>}
      </button>
    );
  }

  function commit() {
    const next = (draft ?? '').trim();
    setDraft(null);
    if (next !== value) onSave(next);
  }

  return (
    <input
      autoFocus
      aria-label={label}
      value={draft}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit();
        if (e.key === 'Escape') setDraft(null);
      }}
      className="h-7 w-full rounded border border-accent bg-surface px-1.5 text-sm outline-none"
    />
  );
}

/** Частота общения: пилюля с поповером пресетов. */
export function FrequencyCell({ days, onChange }: { days: number | null; onChange: (days: number | null) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const pick = (value: number | null) => {
    setIsOpen(false);
    if (value !== days) onChange(value);
  };
  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Pill isActive={Boolean(days)} aria-label={`Частота: ${frequencyLabel(days)}`} onClick={(e) => e.stopPropagation()}>
          {days ? frequencyLabel(days) : 'Задать частоту'}
        </Pill>
      </PopoverTrigger>
      <PopoverContent className="w-52" onClick={(e) => e.stopPropagation()}>
        {FREQUENCY_PRESETS.map((p) => (
          <button key={p.days} type="button" className={optionClass} onClick={() => pick(p.days)}>
            <span className="flex-1">{p.label}</span>
            {p.days === days && <span className="text-accent">✓</span>}
          </button>
        ))}
        {days !== null && (
          <button type="button" className={`${optionClass} text-muted`} onClick={() => pick(null)}>
            Без частоты
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Приоритет: цветная плашка уровня или «Задать», поповер с уровнями. */
export function PriorityCell({ value, onChange }: { value: string; onChange: (level: string) => void }) {
  const [isOpen, setIsOpen] = useState(false);
  const pick = (level: string) => {
    setIsOpen(false);
    if (level !== value) onChange(level);
  };
  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Приоритет: ${priorityLabel(value)}`}
          onClick={(e) => e.stopPropagation()}
          className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        >
          {isPriorityLevel(value) ? (
            <Tag color={PRIORITY_META[value].color}>{PRIORITY_META[value].label}</Tag>
          ) : (
            <Pill>Задать</Pill>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-44" onClick={(e) => e.stopPropagation()}>
        {PRIORITY_LEVELS.map((level) => (
          <button key={level} type="button" className={optionClass} onClick={() => pick(level)}>
            <Tag color={PRIORITY_META[level].color}>{PRIORITY_META[level].label}</Tag>
            {level === value && <span className="ml-auto text-accent">✓</span>}
          </button>
        ))}
        {value && (
          <button type="button" className={`${optionClass} text-muted`} onClick={() => pick('')}>
            Сбросить
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}
