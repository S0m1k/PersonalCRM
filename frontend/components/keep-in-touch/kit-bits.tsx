'use client';

import { useState } from 'react';
import { cn, relativeTime } from '@/lib/utils';
import { dueBadge, type DueBadge, type KitRow } from '@/lib/keep-in-touch';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';

const TONES: Record<DueBadge['tone'], string> = {
  danger: 'bg-danger/10 text-danger',
  warning: 'bg-warning/15 text-warning',
  neutral: 'bg-hover text-muted',
};

export function DueBadgeView({ row, className }: { row: KitRow; className?: string }) {
  const badge = dueBadge(row);
  if (!badge) return null;
  return (
    <span className={cn('inline-flex h-5 items-center whitespace-nowrap rounded-full px-2 text-[11px] font-medium', TONES[badge.tone], className)}>
      {badge.text}
    </span>
  );
}

export function lastInteractionText(row: KitRow): string {
  return row.last_interaction_at ? relativeTime(row.last_interaction_at) : 'Никогда';
}

const MIN_DAYS = 1;
const MAX_DAYS = 730;

/** Диалог «Своя частота»: число дней 1..730. */
export function CustomFrequencyDialog({ row, onClose, onSubmit }: { row: KitRow; onClose: () => void; onSubmit: (days: number) => void }) {
  const [value, setValue] = useState(row.frequency_days ? String(row.frequency_days) : '');
  const days = Number(value);
  const isValid = Number.isInteger(days) && days >= MIN_DAYS && days <= MAX_DAYS;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent title="Своя частота" description={`Как часто общаться: ${row.name}`}>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (isValid) onSubmit(days);
          }}
        >
          <label className="block text-sm">
            Каждые, дней
            <Input type="number" min={MIN_DAYS} max={MAX_DAYS} autoFocus value={value} onChange={(e) => setValue(e.target.value)} className="mt-1" />
          </label>
          {!isValid && value !== '' && <p className="text-xs text-danger">От {MIN_DAYS} до {MAX_DAYS} дней.</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
            <Button type="submit" variant="primary" disabled={!isValid}>Сохранить</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
