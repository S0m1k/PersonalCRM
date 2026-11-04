'use client';

import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (name: string, emoji: string) => Promise<void>;
};

/** Название и эмодзи нового вида; фильтры, сортировку и колонки берёт текущее состояние списка. */
export function SaveViewDialog({ open, onOpenChange, onSave }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Новый вид" description="Сохраняет текущие фильтры, сортировку и колонки. Вид появится в боковой панели.">
        <SaveViewForm
          onCancel={() => onOpenChange(false)}
          onSave={async (n, e) => {
            await onSave(n, e);
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function SaveViewForm({ onCancel, onSave }: { onCancel: () => void; onSave: Props['onSave'] }) {
  const [name, setName] = useState('');
  const [emoji, setEmoji] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setIsSaving(true);
    try {
      await onSave(name.trim(), emoji.trim());
    } catch {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex gap-2">
        <Input aria-label="Эмодзи" placeholder="⭐" maxLength={4} value={emoji} onChange={(e) => setEmoji(e.target.value)} className="w-14 text-center" />
        <Input autoFocus aria-label="Название вида" placeholder="Например, «Друзья без связи»" value={name} onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Отмена
        </Button>
        <Button type="submit" variant="primary" disabled={!name.trim() || isSaving}>
          {isSaving ? 'Сохраняю…' : 'Сохранить'}
        </Button>
      </div>
    </form>
  );
}