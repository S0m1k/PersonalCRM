'use client';

import { RefreshCw, Sparkles } from 'lucide-react';
import { formatDate } from '@/lib/utils';
import { EmptyState, Skeleton } from '@/components/app/page';
import { JobStatus } from '@/components/assistant/job-status';
import type { DossierState } from '@/components/contact/use-dossier';
import { Button } from '@/components/ui/button';

export function DossierTab({ state }: { state: DossierState }) {
  const { dossier, job, isGenerating, isLoading, start, cancel } = state;
  const failed = job && (job.status === 'failed' || job.status === 'cancelled');

  return (
    <div className="pt-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-faint">
          {dossier ? `Составлено ${formatDate(dossier.generated_at.slice(0, 10))} · модель ${dossier.model}` : 'Досье ещё не составлялось'}
        </div>
        <Button variant={dossier ? 'outline' : 'primary'} onClick={() => void start()} disabled={isGenerating}>
          {dossier ? <RefreshCw /> : <Sparkles />} {dossier ? 'Обновить' : 'Составить досье'}
        </Button>
      </div>

      {job && (isGenerating || failed) && (
        <div className="mb-4">
          <JobStatus job={job} onCancel={() => void cancel()} />
        </div>
      )}

      {isLoading && !dossier && <Skeleton className="h-40" />}

      {dossier && (
        <article className="whitespace-pre-line rounded-2xl border border-line bg-surface p-5 text-[15px] leading-relaxed shadow-xs">
          {dossier.text}
        </article>
      )}

      {!isLoading && !dossier && !isGenerating && (
        <EmptyState icon={Sparkles} title="Досье ИИ">
          Короткая сводка «кто это» по всей карточке: заметкам, ответам на вопросы, взаимодействиям и встречам. ИИ
          пишет только по вашим данным и ничего не выдумывает.
        </EmptyState>
      )}
    </div>
  );
}
