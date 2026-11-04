'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { applyStrategy, previewApply, type ApplyPreview } from '@/lib/api-goals';
import { frequencyLabel } from '@/lib/frequency';
import { errorText, plural } from '@/lib/utils';

const SHOWN_ITEMS = 8;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplied: () => void;
}

/** Предпросмотр «Применить к контактам»: сколько людей получат какую частоту; применение по подтверждению. */
export function ApplyDialog({ open, onOpenChange, onApplied }: Props) {
  const [overwrite, setOverwrite] = useState(false);
  const [applying, setApplying] = useState(false);
  const { data: preview, isLoading: loading } = useSWR<ApplyPreview>(
    open ? ['goals-apply-preview', overwrite] : null,
    () => previewApply(overwrite),
    { revalidateOnFocus: false, shouldRetryOnError: false, onError: (err) => toast.error(errorText(err)) },
  );

  async function apply() {
    setApplying(true);
    try {
      const r = await applyStrategy(overwrite);
      toast.success(`Частота обновлена у ${r.changed} ${plural(r.changed, 'контакта', 'контактов', 'контактов')}`);
      onApplied();
      onOpenChange(false);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setApplying(false);
    }
  }

  const changes = preview?.items.filter((i) => i.action === 'change') ?? [];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Применить к контактам" description="Стратегия проставит рекомендованную частоту общения (Keep in Touch).">
        {loading && !preview ? (
          <p className="text-sm text-muted">Считаем…</p>
        ) : preview ? (
          <div className="space-y-3 text-sm">
            {preview.by_frequency.length === 0 ? (
              <p className="text-muted">Менять нечего: у всех подходящих контактов частота уже такая, или стратегия не выбрана.</p>
            ) : (
              <ul className="space-y-1">
                {preview.by_frequency.map((f) => (
                  <li key={f.frequency_days}>
                    <b>{f.count}</b> {plural(f.count, 'контакт получит', 'контакта получат', 'контактов получат')} частоту «{frequencyLabel(f.frequency_days)}»
                  </li>
                ))}
              </ul>
            )}
            {changes.length > 0 && (
              <ul className="max-h-40 divide-y divide-line overflow-y-auto rounded-xl border border-line">
                {changes.slice(0, SHOWN_ITEMS).map((i) => (
                  <li key={i.contact_id} className="flex justify-between gap-2 px-3 py-1.5">
                    <span className="truncate">{i.name}</span>
                    <span className="shrink-0 text-muted">{frequencyLabel(i.current)} → {frequencyLabel(i.recommended)}</span>
                  </li>
                ))}
                {changes.length > SHOWN_ITEMS && <li className="px-3 py-1.5 text-muted">и ещё {changes.length - SHOWN_ITEMS}</li>}
              </ul>
            )}
            <p className="text-muted">
              Без изменений: {preview.unchanged}. Заданы вручную и не тронуты: {preview.skipped_manual}.
            </p>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
              Перезаписать и частоты, заданные вручную
            </label>
            <div className="flex justify-end gap-2 pt-1">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>Отмена</Button>
              <Button variant="primary" disabled={applying || preview.will_change === 0} onClick={apply}>
                Применить ({preview.will_change})
              </Button>
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
