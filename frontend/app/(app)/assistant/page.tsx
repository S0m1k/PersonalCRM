'use client';

import { useState, type FormEvent, type KeyboardEvent } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { MessageCircle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';
import {
  applyCapture,
  assistantInfoKey,
  assistantJobKey,
  cancelAssistantJob,
  startAsk,
  startCapture,
  type ApplyResult,
  type AskResult,
  type AssistantInfo,
  type AssistantJob,
  type CaptureResult,
} from '@/lib/api';
import { cn, errorText } from '@/lib/utils';
import { Page, PageHeader } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/input';
import { CapturePreview } from '@/components/assistant/capture-preview';
import { JobStatus, isPending } from '@/components/assistant/job-status';

type Mode = 'capture' | 'ask';

const POLL_MS = 1500;

const MODES: { value: Mode; label: string; placeholder: string; hint: string }[] = [
  {
    value: 'capture',
    label: 'Записать',
    placeholder: 'Встретил Петю, дочке 5 лет, переезжает в Дубай',
    hint: 'Помощник разложит запись по карточке — вы увидите изменения и примените их одним кликом.',
  },
  {
    value: 'ask',
    label: 'Спросить',
    placeholder: 'Что я хотел спросить у Пети?',
    hint: 'Ответ — только по вашим контактам, с ссылками на карточки. Ничего не меняется.',
  },
];

export default function AssistantPage() {
  const [mode, setMode] = useState<Mode>('capture');
  const [text, setText] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [applied, setApplied] = useState<ApplyResult | null>(null);
  const { mutate: mutateGlobal } = useSWRConfig();
  const { data: info } = useSWR<AssistantInfo>(assistantInfoKey);
  const { data: job, mutate: mutateJob } = useSWR<AssistantJob>(jobId ? assistantJobKey(jobId) : null, {
    refreshInterval: (latest) => (isPending(latest) || !latest ? POLL_MS : 0),
  });

  const current = MODES.find((m) => m.value === mode) ?? MODES[0];
  const busy = isSubmitting || isPending(job);

  function reset() {
    setJobId(null);
    setApplied(null);
  }

  function switchMode(next: Mode) {
    if (next === mode) return;
    setMode(next);
    reset();
  }

  async function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setIsSubmitting(true);
    reset();
    try {
      const created = mode === 'capture' ? await startCapture(value) : await startAsk(value);
      setJobId(created.id);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) void handleSubmit();
  }

  async function handleCancel() {
    if (!jobId) return;
    try {
      await mutateJob(await cancelAssistantJob(jobId), { revalidate: false });
      reset();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleApply(actions: number[], contactId: string | null) {
    if (!jobId) return;
    setIsApplying(true);
    try {
      const outcome = await applyCapture(jobId, actions, contactId);
      setApplied(outcome);
      setText('');
      // Карточки, вопросы и счётчики на главной поменялись
      void mutateGlobal(
        (k) => typeof k === 'string' && (k.startsWith('/api/contacts') || k.startsWith('/api/questions') || k.startsWith('/api/home')),
      );
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsApplying(false);
    }
  }

  return (
    <Page>
      <PageHeader
        icon={MessageCircle}
        title="Помощник"
        description={
          <>
            {current.hint}
            {info && <span className="text-faint"> Модель: {info.model}.</span>}
          </>
        }
      />

      <div className="mb-4 flex gap-1" role="tablist">
        {MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            role="tab"
            aria-selected={mode === m.value}
            onClick={() => switchMode(m.value)}
            className={cn(
              'h-7 rounded-full px-3 text-sm transition-colors',
              mode === m.value ? 'bg-fg text-bg' : 'text-muted hover:bg-hover hover:text-fg',
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="mb-6 flex flex-col gap-2">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={current.placeholder}
          maxLength={mode === 'capture' ? 2000 : 500}
          aria-label={current.label}
          className="min-h-24 text-[15px]"
        />
        <div className="flex items-center gap-3">
          <Button type="submit" variant="primary" disabled={!text.trim() || busy}>
            <Sparkles />
            {mode === 'capture' ? 'Разобрать' : 'Спросить'}
          </Button>
          <span className="text-xs text-faint">Ctrl + Enter</span>
        </div>
      </form>

      {job && <JobStatus job={job} onCancel={handleCancel} />}

      {job?.status === 'done' || job?.status === 'applied' ? (
        job.kind === 'capture' ? (
          <CapturePreview
            key={job.id}
            result={job.result as CaptureResult}
            applied={applied}
            busy={isApplying}
            onApply={handleApply}
            onDiscard={reset}
          />
        ) : (
          <AskAnswer result={job.result as AskResult} />
        )
      ) : null}
    </Page>
  );
}

function AskAnswer({ result }: { result: AskResult }) {
  return (
    <div className="rounded-md border border-line bg-surface px-4 py-3">
      <p className="whitespace-pre-line text-[15px] leading-relaxed">{result.answer}</p>
      {result.contacts.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {result.contacts.map((c) => (
            <Link
              key={c.id}
              href={`/contacts/${c.id}`}
              className="inline-flex h-6 items-center rounded-full border border-line px-2.5 text-sm text-muted hover:bg-hover hover:text-fg"
            >
              {c.name}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
