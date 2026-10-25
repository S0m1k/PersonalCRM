'use client';

import { CircleAlert, Hourglass, LoaderCircle } from 'lucide-react';
import type { AssistantJob } from '@/lib/api';
import { Button } from '@/components/ui/button';

/** Задача ещё не готова или упала: место в очереди, «думает…», ошибка. */
export function JobStatus({ job, onCancel }: { job: AssistantJob; onCancel: () => void }) {
  if (job.status === 'queued') {
    return (
      <div className="flex items-center gap-2.5 rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-muted">
        <Hourglass className="size-4 shrink-0 text-faint" />
        <span className="flex-1">
          В очереди{job.position && job.position > 1 ? ` — перед вами ${job.position - 1}` : ''}. Модель работает
          по одному запросу за раз.
        </span>
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Отменить
        </Button>
      </div>
    );
  }
  if (job.status === 'running') {
    return (
      <div className="flex items-center gap-2.5 rounded-md border border-line bg-surface px-3 py-2.5 text-sm text-muted">
        <LoaderCircle className="size-4 shrink-0 animate-spin text-accent" />
        Думаю… обычно до 10 секунд, первый запрос после перерыва — до минуты.
      </div>
    );
  }
  if (job.status === 'failed') {
    return (
      <div className="flex items-center gap-2.5 rounded-md border border-danger/30 bg-danger/5 px-3 py-2.5 text-sm text-danger">
        <CircleAlert className="size-4 shrink-0" />
        {job.error || 'Не получилось'}
      </div>
    );
  }
  return null;
}

export function isPending(job: AssistantJob | undefined): boolean {
  return job?.status === 'queued' || job?.status === 'running';
}
