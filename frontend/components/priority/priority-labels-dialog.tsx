'use client';

import { useState } from 'react';
import { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { priorityLabelsKey, savePriorityLabels, type PriorityLabels } from '@/lib/api-preferences';
import { PRIORITY_LEVELS, PRIORITY_META } from '@/lib/priority';
import { errorText } from '@/lib/utils';

export const LABEL_MAX_LEN = 24;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  labels: PriorityLabels | undefined;
}

function Form({ labels, onDone }: { labels: PriorityLabels | undefined; onDone: () => void }) {
  const { mutate } = useSWRConfig();
  const [draft, setDraft] = useState<PriorityLabels>(
    () => labels ?? (Object.fromEntries(PRIORITY_LEVELS.map((l) => [l, PRIORITY_META[l].label])) as PriorityLabels),
  );
  const [isSaving, setIsSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    try {
      await mutate(priorityLabelsKey(), savePriorityLabels(draft), { revalidate: false });
      toast.success('Названия сохранены');
      onDone();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      {PRIORITY_LEVELS.map((level) => (
        <label key={level} className="block text-sm">
          <span className="text-muted">{PRIORITY_META[level].label}</span>
          <Input
            value={draft[level]}
            maxLength={LABEL_MAX_LEN}
            onChange={(e) => setDraft({ ...draft, [level]: e.target.value })}
            placeholder={PRIORITY_META[level].label}
          />
        </label>
      ))}
      <p className="text-xs text-muted">До {LABEL_MAX_LEN} символов. Пустое поле вернёт стандартное название.</p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onDone}>Отмена</Button>
        <Button type="submit" variant="primary" disabled={isSaving}>Сохранить</Button>
      </div>
    </form>
  );
}

/** Переименование уровней Priority Map (хранится на сервере для пользователя). */
export function PriorityLabelsDialog({ open, onOpenChange, labels }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Названия уровней" description="Свои подписи для кругов Priority Map.">
        <Form labels={labels} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
