'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { assistantJobKey, cancelAssistantJob, type AssistantJob } from '@/lib/api';
import { dossierKey, getDossier, startDossier, type Dossier } from '@/lib/api-assistant';
import { errorText } from '@/lib/utils';
import { isPending } from '@/components/assistant/job-status';

const POLL_MS = 1500;

/** Досье контакта: последний текст, задача составления (с опросом) и запуск. */
export function useDossier(contactId: string) {
  const { data: dossier, isLoading, mutate } = useSWR<Dossier | null>(dossierKey(contactId), () => getDossier(contactId));
  const [jobId, setJobId] = useState<string | null>(null);
  const { data: job, mutate: mutateJob } = useSWR<AssistantJob<Dossier>>(jobId ? assistantJobKey(jobId) : null, {
    refreshInterval: (latest) => (isPending(latest) || !latest ? POLL_MS : 0),
    onSuccess: (latest) => {
      if (latest.status === 'done') {
        setJobId(null);
        void mutate();
      }
    },
  });

  async function start() {
    try {
      const started = await startDossier(contactId);
      setJobId(started.id);
      void mutateJob(started, { revalidate: false });
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function cancel() {
    if (!jobId) return;
    try {
      await cancelAssistantJob(jobId);
    } catch (err) {
      toast.error(errorText(err));
    }
    setJobId(null);
  }

  const activeJob = jobId ? job : undefined;
  const isGenerating = Boolean(jobId) && (!job || isPending(job));
  return { dossier: dossier ?? null, isLoading, job: activeJob, isGenerating, start, cancel };
}

export type DossierState = ReturnType<typeof useDossier>;
