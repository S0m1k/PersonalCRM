'use client';

import { useState } from 'react';
import { Check, ChevronDown, Heart, Network, PieChart, SlidersHorizontal, type LucideIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { ApproachId, ApproachInfo } from '@/lib/api-goals';

const ICONS: Record<string, LucideIcon> = { network: Network, heart: Heart, pie: PieChart, sliders: SlidersHorizontal };

interface Props {
  catalogue: ApproachInfo[];
  primary: ApproachId | null;
  enabled: ApproachId[];
  selected: ApproachId;
  busy: boolean;
  onSelect: (id: ApproachId) => void;
  onSetPrimary: (id: ApproachId) => void;
  onToggleExtra: (id: ApproachId) => void;
}

/** Большие карточки подходов: выбор для просмотра, «Основной» / «Дополнительный», «Подробнее». */
export function ApproachPicker({ catalogue, primary, enabled, selected, busy, onSelect, onSetPrimary, onToggleExtra }: Props) {
  const [open, setOpen] = useState<ApproachId | null>(null);

  return (
    <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Подход к отношениям">
      {catalogue.map((a) => {
        const Icon = ICONS[a.icon] ?? Network;
        const isPrimary = primary === a.id;
        const isExtra = enabled.includes(a.id);
        const isSelected = selected === a.id;
        const expanded = open === a.id;
        return (
          <div
            key={a.id}
            className={cn(
              'flex flex-col rounded-2xl border bg-surface p-4 shadow-xs transition-colors',
              isSelected ? 'border-accent ring-[3px] ring-accent/15' : 'border-line hover:border-line-strong',
            )}
          >
            <button
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => onSelect(a.id)}
              className="flex flex-1 items-start gap-3 rounded-lg text-left"
            >
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-line bg-sidebar text-accent">
                <Icon className="size-5" strokeWidth={1.6} aria-hidden />
              </span>
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-xl font-semibold leading-tight">{a.name}</span>
                  {isPrimary && <Badge>Основной</Badge>}
                  {isExtra && <Badge muted>Дополнительный</Badge>}
                </span>
                <span className="mt-1 block text-sm text-muted">{a.tagline}</span>
              </span>
            </button>

            {expanded && (
              <div className="mt-3 space-y-3 border-t border-line pt-3 text-sm">
                <p className="text-muted">{a.philosophy}</p>
                <Bullets title="Принципы" items={a.principles} />
                <Bullets title="Что сделает стратегия" items={a.does} />
                <Bullets title="Метрики" items={a.metrics} />
              </div>
            )}

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button size="sm" variant={isPrimary ? 'primary' : 'outline'} disabled={busy || isPrimary} onClick={() => onSetPrimary(a.id)}>
                {isPrimary && <Check aria-hidden />}Основной
              </Button>
              <Button
                size="sm"
                variant={isExtra ? 'secondary' : 'outline'}
                disabled={busy || isPrimary}
                aria-pressed={isExtra}
                onClick={() => onToggleExtra(a.id)}
              >
                {isExtra && <Check aria-hidden />}Дополнительный
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="ml-auto"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : a.id)}
              >
                Подробнее
                <ChevronDown className={cn('transition-transform', expanded && 'rotate-180')} aria-hidden />
              </Button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Badge({ children, muted = false }: { children: string; muted?: boolean }) {
  return (
    <span
      className={cn(
        'rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-[0.06em]',
        muted ? 'bg-olive-100 text-olive-600' : 'bg-accent-50 text-accent-700 dark:bg-accent-950 dark:text-accent-200',
      )}
    >
      {children}
    </span>
  );
}

function Bullets({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">{title}</div>
      <ul className="list-disc space-y-0.5 pl-5">
        {items.map((i) => (
          <li key={i}>{i}</li>
        ))}
      </ul>
    </div>
  );
}
