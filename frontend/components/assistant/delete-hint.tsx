'use client';

import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';

/** «Записать» получило команду удаления: помощник удалять не умеет и ничего не создавал и не менял. */
export function DeleteHint({ busy, onRecordAnyway }: { busy: boolean; onRecordAnyway: () => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-md border border-line bg-surface px-3 py-2.5 text-sm">
      <Trash2 className="size-4 shrink-0 text-muted" />
      <span className="flex-1 text-muted">
        Удалять контакты помощник не умеет, поэтому ничего не создано и не изменено. Откройте карточку человека → «…» →
        «Удалить контакт».
      </span>
      <Button size="sm" variant="ghost" onClick={onRecordAnyway} disabled={busy}>
        Всё равно записать
      </Button>
    </div>
  );
}
