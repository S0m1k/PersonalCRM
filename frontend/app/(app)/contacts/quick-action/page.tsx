'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { toast } from 'sonner';
import { ArrowRight, Check, CircleCheck, SkipForward, Undo2, Zap } from 'lucide-react';
import { apiFetch, getContacts, updateContact, type Contact, type ContactUpdate } from '@/lib/api';
import { FREQUENCY_PRESETS, frequencyLabel } from '@/lib/frequency';
import { PRIORITY_LEVELS, PRIORITY_META, priorityLabel } from '@/lib/priority';
import { cn, errorText, fullName, relativeTime } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { Page, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Kbd, Tag } from '@/components/ui/tag';

const QUEUE_LIMIT = 200;
const PRIORITY_KEYS: Record<string, string> = { Digit1: 'top', Digit2: 'high', Digit3: 'medium', Digit4: 'low', Digit5: 'none' };
const FREQUENCY_KEYS: Record<string, number> = Object.fromEntries(
  FREQUENCY_PRESETS.map((p) => [`Key${p.hotkey.toUpperCase()}`, p.days]),
);

type Stage = 'intro' | 'play' | 'done';
type Action = { id: string; field: 'priority' | 'frequency' | 'skip'; prev: string | number | null; advanced: boolean };

async function loadQueue(): Promise<{ queue: Contact[]; noPriority: number; noFrequency: number }> {
  const [byPriority, byFrequency, np, nf] = await Promise.all([
    getContacts({ has_priority: false, sort: 'importance', limit: QUEUE_LIMIT }),
    getContacts({ has_frequency: false, sort: 'importance', limit: QUEUE_LIMIT }),
    countOf('has_priority=false'),
    countOf('has_frequency=false'),
  ]);
  const seen = new Set<string>();
  const queue = [...byPriority, ...byFrequency].filter((c) => !seen.has(c.id) && seen.add(c.id));
  return { queue, noPriority: np, noFrequency: nf };
}

async function countOf(query: string): Promise<number> {
  return (await apiFetch<{ count: number }>(`/api/contacts/count?${query}`)).count;
}

export default function QuickActionPage() {
  const { data, isLoading, mutate } = useSWR('quick-action:queue', loadQueue, { revalidateOnFocus: false });
  const [stage, setStage] = useState<Stage>('intro');
  const [queue, setQueue] = useState<Contact[]>([]);
  const [index, setIndex] = useState(0);
  const [history, setHistory] = useState<Action[]>([]);
  const [skipped, setSkipped] = useState(0);
  const [changes, setChanges] = useState({ priority: 0, frequency: 0 });

  const current = queue[index];

  function start() {
    if (!data?.queue.length) return;
    setQueue(data.queue);
    setIndex(0);
    setHistory([]);
    setSkipped(0);
    setChanges({ priority: 0, frequency: 0 });
    setStage('play');
  }

  function finish() {
    setStage('done');
    void mutate();
  }

  const save = useCallback(async (id: string, patch: ContactUpdate) => {
    try {
      await updateContact(id, patch);
    } catch (err) {
      toast.error(errorText(err));
    }
  }, []);

  const patchLocal = (id: string, patch: Partial<Contact>) =>
    setQueue((q) => q.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const advance = useCallback(() => {
    if (index + 1 >= queue.length) setStage('done');
    else setIndex((i) => i + 1);
  }, [index, queue.length]);

  const setPriority = useCallback(
    (level: string) => {
      if (!current) return;
      const done = Boolean(current.keep_in_touch.frequency_days);
      setHistory((h) => [...h, { id: current.id, field: 'priority', prev: current.priority || null, advanced: done }]);
      setChanges((c) => ({ ...c, priority: c.priority + 1 }));
      patchLocal(current.id, { priority: level });
      void save(current.id, { priority: level });
      if (done) advance();
    },
    [current, advance, save],
  );

  const setFrequency = useCallback(
    (days: number) => {
      if (!current) return;
      const done = Boolean(current.priority);
      setHistory((h) => [...h, { id: current.id, field: 'frequency', prev: current.keep_in_touch.frequency_days, advanced: done }]);
      setChanges((c) => ({ ...c, frequency: c.frequency + 1 }));
      const keep = { frequency_days: days, snoozed_until: current.keep_in_touch.snoozed_until };
      patchLocal(current.id, { keep_in_touch: keep });
      void save(current.id, { keep_in_touch: keep });
      if (done) advance();
    },
    [current, advance, save],
  );

  const skip = useCallback(() => {
    if (!current) return;
    setHistory((h) => [...h, { id: current.id, field: 'skip', prev: null, advanced: true }]);
    setSkipped((s) => s + 1);
    advance();
  }, [current, advance]);

  const undo = useCallback(() => {
    const last = history[history.length - 1];
    if (!last) return;
    setHistory((h) => h.slice(0, -1));
    if (last.field === 'skip') setSkipped((s) => s - 1);
    else {
      const field = last.field;
      setChanges((c) => ({ ...c, [field]: c[field] - 1 }));
      const target = queue.find((c) => c.id === last.id);
      if (last.field === 'priority') {
        patchLocal(last.id, { priority: (last.prev as string) ?? '' });
        void save(last.id, { priority: (last.prev as string) ?? '' });
      } else if (target) {
        const keep = { frequency_days: last.prev as number | null, snoozed_until: target.keep_in_touch.snoozed_until };
        patchLocal(last.id, { keep_in_touch: keep });
        void save(last.id, { keep_in_touch: keep });
      }
    }
    if (last.advanced) {
      if (stage === 'done') setStage('play');
      else setIndex((i) => Math.max(0, i - 1));
    }
  }, [history, queue, save, stage]);

  const startRef = useRef(start);
  useEffect(() => {
    startRef.current = start;
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (e.metaKey || e.ctrlKey || e.altKey || target?.closest('input, textarea, select, [role="dialog"]')) return;
      if (stage === 'intro' && e.key === 'Enter') {
        e.preventDefault();
        startRef.current();
        return;
      }
      if (stage !== 'play' && !(stage === 'done' && e.key === 'Backspace')) return;
      if (e.key === 'Backspace') undo();
      else if (e.key === 'ArrowRight' || e.code === 'KeyS') skip();
      else if (e.code in PRIORITY_KEYS) setPriority(PRIORITY_KEYS[e.code]);
      else if (e.code in FREQUENCY_KEYS) setFrequency(FREQUENCY_KEYS[e.code]);
      else return;
      e.preventDefault();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stage, undo, skip, setPriority, setFrequency]);

  return (
    <Page>
      {isLoading && <Skeleton className="mx-auto mt-10 h-72 max-w-md" />}
      {data && stage === 'intro' && <Intro data={data} onStart={start} />}
      {stage === 'play' && current && (
        <Play
          contact={current}
          index={index}
          total={queue.length}
          canUndo={history.length > 0}
          onPriority={setPriority}
          onFrequency={setFrequency}
          onSkip={skip}
          onUndo={undo}
          onFinish={finish}
        />
      )}
      {stage === 'done' && (
        <Done reviewed={history.length - skipped} skipped={skipped} changes={changes} canUndo={history.length > 0} onUndo={undo} onRestart={() => { setStage('intro'); void mutate(); }} />
      )}
    </Page>
  );
}

// ---------------------------------------------------------------- intro

function Intro({ data, onStart }: { data: { queue: Contact[]; noPriority: number; noFrequency: number }; onStart: () => void }) {
  const stack = data.queue.slice(0, 3);
  const isEmpty = data.queue.length === 0;
  return (
    <div className="flex flex-col items-center pt-6 text-center animate-fade-up">
      <div className="relative mb-10 h-44 w-72" aria-hidden>
        {[...stack].reverse().map((c, i, arr) => {
          const depth = arr.length - 1 - i;
          return (
            <div
              key={c.id}
              className="absolute inset-x-0 top-0 flex h-36 flex-col items-center justify-center gap-1 rounded-2xl border border-line bg-surface shadow-md"
              style={{ transform: `translateY(${depth * 12}px) scale(${1 - depth * 0.05}) rotate(${(depth % 2 ? 1 : -1) * depth * 1.5}deg)`, zIndex: i }}
            >
              <Avatar name={fullName(c) || '?'} size="lg" />
              <span className="text-sm font-medium">{fullName(c) || 'Без имени'}</span>
              <span className="text-xs text-muted">{c.position || c.company || ' '}</span>
            </div>
          );
        })}
        {stack.length === 0 && <div className="absolute inset-0 flex items-center justify-center rounded-2xl border border-dashed border-line-strong"><Zap className="size-8 text-faint" /></div>}
      </div>
      <h1 className="font-display text-title">Быстрые действия</h1>
      <p className="mt-2 max-w-sm text-[15px] text-muted">
        Расставьте приоритет и частоту общения с людьми одним нажатием клавиши — карточка за карточкой.
      </p>
      <Button variant="primary" className="mt-6" onClick={onStart} disabled={isEmpty}>
        Начать <Kbd className="ml-1 border-accent-fg/30 bg-transparent text-accent-fg">Enter</Kbd>
      </Button>
      <p className="mt-4 text-sm text-muted tabular">
        {data.noPriority} без приоритета · {data.noFrequency} без частоты
      </p>
      {isEmpty && <p className="mt-2 text-sm text-muted">Все контакты уже разобраны.</p>}
    </div>
  );
}

// ---------------------------------------------------------------- play

type PlayProps = {
  contact: Contact;
  index: number;
  total: number;
  canUndo: boolean;
  onPriority: (level: string) => void;
  onFrequency: (days: number) => void;
  onSkip: () => void;
  onUndo: () => void;
  onFinish: () => void;
};

function Play({ contact: c, index, total, canUndo, onPriority, onFrequency, onSkip, onUndo, onFinish }: PlayProps) {
  const name = fullName(c) || 'Без имени';
  const subtitle = [c.position, c.company].filter(Boolean).join(' · ');
  const freq = c.keep_in_touch.frequency_days;
  const progress = Math.round((index / total) * 100);

  return (
    <div className="mx-auto max-w-lg">
      <div className="mb-6 flex items-center gap-3">
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={index}
          aria-label="Прогресс"
          className="h-1.5 flex-1 overflow-hidden rounded-full bg-line"
        >
          <div className="h-full rounded-full bg-accent transition-[width] duration-300" style={{ width: `${progress}%` }} />
        </div>
        <span className="text-xs text-muted tabular">{index + 1} / {total}</span>
        <Button variant="ghost" size="sm" onClick={onFinish}>
          Завершить
        </Button>
      </div>

      <div key={c.id} className="rounded-2xl border border-line bg-surface p-6 text-center shadow-md animate-fade-up">
        <div className="flex justify-center">
          <Avatar name={name} size="xl" />
        </div>
        <h2 className="mt-3 font-display text-2xl font-semibold">
          <Link href={`/contacts/${c.id}`} className="hover:underline">{name}</Link>
        </h2>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
        {c.description && <p className="mx-auto mt-3 max-w-sm text-sm">{c.description}</p>}
        <p className="mt-3 text-xs text-muted">
          Последнее взаимодействие: {c.last_interaction_at ? relativeTime(c.last_interaction_at) : 'никогда'}
        </p>
      </div>

      <section aria-label="Приоритет" className="mt-6">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Приоритет</h3>
        <div className="flex flex-wrap gap-1.5">
          {PRIORITY_LEVELS.map((level) => (
            <ChoiceButton key={level} isActive={c.priority === level} hotkey={PRIORITY_META[level].hotkey} onClick={() => onPriority(level)}>
              {priorityLabel(level)}
            </ChoiceButton>
          ))}
        </div>
      </section>

      <section aria-label="Частота общения" className="mt-5">
        <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Как часто общаться</h3>
        <div className="flex flex-wrap gap-1.5">
          {FREQUENCY_PRESETS.map((p) => (
            <ChoiceButton key={p.days} isActive={freq === p.days} hotkey={p.hotkey.toUpperCase()} onClick={() => onFrequency(p.days)} title={frequencyLabel(p.days)}>
              {p.short}
            </ChoiceButton>
          ))}
        </div>
      </section>

      <div className="mt-8 flex items-center justify-between">
        <Button variant="ghost" onClick={onUndo} disabled={!canUndo}>
          <Undo2 /> Отменить <Kbd>⌫</Kbd>
        </Button>
        <Button variant="outline" onClick={onSkip}>
          <SkipForward /> Пропустить <Kbd>S</Kbd>
        </Button>
      </div>
    </div>
  );
}

function ChoiceButton({
  isActive,
  hotkey,
  children,
  ...props
}: { isActive: boolean; hotkey: string } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={isActive}
      className={cn(
        'inline-flex h-9 items-center gap-2 rounded-lg border px-3 text-sm transition-colors',
        isActive ? 'border-accent bg-accent/10 font-medium text-fg' : 'border-line bg-surface text-muted hover:bg-hover hover:text-fg',
      )}
      {...props}
    >
      {children}
      <Kbd>{hotkey}</Kbd>
    </button>
  );
}

// ---------------------------------------------------------------- done

function Done({ reviewed, skipped, changes, canUndo, onUndo, onRestart }: { reviewed: number; skipped: number; changes: { priority: number; frequency: number }; canUndo: boolean; onUndo: () => void; onRestart: () => void }) {
  const stats = [
    { label: 'Обработано', value: reviewed },
    { label: 'Приоритетов задано', value: changes.priority },
    { label: 'Частот задано', value: changes.frequency },
    { label: 'Пропущено', value: skipped },
  ];
  return (
    <div className="flex flex-col items-center pt-10 text-center animate-fade-up">
      <CircleCheck className="size-12 text-success" aria-hidden />
      <h1 className="mt-4 font-display text-title">Готово</h1>
      <p className="mt-2 text-[15px] text-muted">Приоритеты и частоты сохранены.</p>
      <dl className="mt-8 grid w-full max-w-md grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.label} className="rounded-xl border border-line bg-surface p-3">
            <dd className="font-display text-3xl font-semibold tabular">{s.value}</dd>
            <dt className="text-xs text-muted">{s.label}</dt>
          </div>
        ))}
      </dl>
      <div className="mt-8 flex gap-2">
        <Button variant="ghost" onClick={onUndo} disabled={!canUndo}>
          <Undo2 /> Отменить последнее
        </Button>
        <Button variant="primary" onClick={onRestart}>
          <Check /> К началу
        </Button>
        <Button variant="outline" asChild>
          <Link href="/contacts">
            К контактам <ArrowRight />
          </Link>
        </Button>
      </div>
    </div>
  );
}
