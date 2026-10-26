'use client';

import { CircleHelp } from 'lucide-react';
import { Button } from '@/components/ui/button';

/** «Записать» получило вопрос: модель не вызывалась, предлагаем спросить или записать всё равно. */
export function QuestionHint({
  busy,
  onAsk,
  onRecordAnyway,
}: {
  busy: boolean;
  onAsk: () => void;
  onRecordAnyway: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2.5 rounded-md border border-line bg-surface px-3 py-2.5 text-sm">
      <CircleHelp className="size-4 shrink-0 text-accent" />
      <span className="flex-1 text-muted">Похоже на вопрос. «Записать» меняет карточки, а ответ даёт «Спросить».</span>
      <Button size="sm" variant="primary" onClick={onAsk} disabled={busy}>
        Спросить
      </Button>
      <Button size="sm" variant="ghost" onClick={onRecordAnyway} disabled={busy}>
        Всё равно записать
      </Button>
    </div>
  );
}
