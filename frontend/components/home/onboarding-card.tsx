'use client';

import { useSyncExternalStore } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { Check, Map as MapIcon, X } from 'lucide-react';
import type { Contact, HomeSummary, SyncConnection } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Card, CardHeader } from '@/components/ui/card';

const DISMISS_KEY = 'crm_home_onboarding_dismissed';
const CONTACTS_SAMPLE_KEY = '/api/contacts/?limit=200';

function subscribe(onChange: () => void): () => void {
  window.addEventListener('storage', onChange);
  window.addEventListener('crm-onboarding', onChange);
  return () => {
    window.removeEventListener('storage', onChange);
    window.removeEventListener('crm-onboarding', onChange);
  };
}

function useDismissed(): [boolean, () => void] {
  const isDismissed = useSyncExternalStore(
    subscribe,
    () => localStorage.getItem(DISMISS_KEY) === '1',
    () => true,
  );
  return [
    isDismissed,
    () => {
      localStorage.setItem(DISMISS_KEY, '1');
      window.dispatchEvent(new Event('crm-onboarding'));
    },
  ];
}

type Step = { label: string; href: string; isDone: boolean };

/** Правая колонка главной (≥ xl): чек-лист «С чего начать», считается по данным, + промо карты. */
export function HomeSidePanel({ home }: { home: HomeSummary | undefined }) {
  const [isDismissed, dismiss] = useDismissed();
  const { data: connections } = useSWR<SyncConnection[]>('/api/sync/connections');
  const { data: sample } = useSWR<Contact[]>(CONTACTS_SAMPLE_KEY);

  const steps: Step[] = [
    { label: 'Добавьте контакты', href: '/import', isDone: (home?.stats.contacts ?? 0) > 0 },
    { label: 'Подключите синхронизацию', href: '/sync', isDone: (connections?.length ?? 0) > 0 },
    {
      label: 'Задайте частоту общения',
      href: '/contacts/quick-action',
      isDone: Boolean(sample?.some((c) => c.keep_in_touch?.frequency_days)),
    },
    {
      label: 'Расставьте приоритеты',
      href: '/priority-map',
      isDone: Boolean(sample?.some((c) => c.importance !== null && c.importance !== undefined)),
    },
    { label: 'Создайте группы', href: '/network', isDone: (home?.counts.groups ?? 0) > 0 },
  ];
  const doneCount = steps.filter((s) => s.isDone).length;
  const isReady = home !== undefined && connections !== undefined && sample !== undefined;

  return (
    <aside className="hidden w-72 shrink-0 flex-col gap-4 xl:flex" aria-label="Подсказки">
      {!isDismissed && isReady && (
        <Card>
          <CardHeader
            label="С чего начать"
            action={
              <button
                type="button"
                onClick={dismiss}
                aria-label="Скрыть «С чего начать»"
                className="rounded p-0.5 text-faint hover:bg-hover hover:text-fg"
              >
                <X className="size-4" />
              </button>
            }
          />
          <p className="mb-3 text-xs text-muted">
            {doneCount} из {steps.length} шагов
          </p>
          <ul className="flex flex-col gap-0.5">
            {steps.map((step) => (
              <li key={step.label}>
                <Link href={step.href} className="-mx-2 flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-hover">
                  <span
                    aria-hidden
                    className={cn(
                      'flex size-[18px] shrink-0 items-center justify-center rounded-full border-[1.5px]',
                      step.isDone ? 'border-accent bg-accent text-accent-fg' : 'border-faint',
                    )}
                  >
                    {step.isDone && <Check className="size-3" strokeWidth={3} />}
                  </span>
                  <span className={cn(step.isDone && 'text-muted line-through')}>{step.label}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
      <Link href="/map" className="group block">
        <Card className="bg-olive-100 transition-shadow group-hover:shadow-md">
          <MapIcon className="mb-2 size-5 text-accent" aria-hidden />
          <div className="font-display text-xl font-semibold leading-tight">Карта — ваша сеть на карте</div>
          <p className="mt-1 text-xs text-muted">Посмотрите, где живут ваши контакты, и кто рядом.</p>
        </Card>
      </Link>
    </aside>
  );
}
