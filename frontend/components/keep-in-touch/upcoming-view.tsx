'use client';

import Link from 'next/link';
import type { KitRow } from '@/lib/keep-in-touch';
import { Avatar } from '@/components/app/avatar';
import { SectionTitle } from '@/components/app/page';
import { frequencyLabel } from '@/lib/frequency';
import { DueBadgeView, lastInteractionText } from './kit-bits';
import { RowActions } from './row-actions';

interface Section {
  title: string;
  rows: KitRow[];
}

/** Секции «Ближайших»: Просрочено / Сегодня / На этой неделе / Позже / Отложено. */
export function sectionsFor(rows: KitRow[]): Section[] {
  const dueSoon = rows.filter((r) => r.status === 'soon');
  return [
    { title: 'Просрочено', rows: rows.filter((r) => r.status === 'overdue') },
    { title: 'Сегодня', rows: dueSoon.filter((r) => r.days_until === 0) },
    { title: 'На этой неделе', rows: dueSoon.filter((r) => r.days_until > 0) },
    { title: 'Позже', rows: rows.filter((r) => r.status === 'upcoming') },
    { title: 'Отложено', rows: rows.filter((r) => r.status === 'snoozed') },
  ].filter((s) => s.rows.length > 0);
}

export function KitUpcoming({ rows }: { rows: KitRow[] }) {
  return (
    <div className="space-y-6">
      {sectionsFor(rows).map((section) => (
        <section key={section.title} aria-label={section.title}>
          <SectionTitle aside={<span className="text-xs tabular-nums text-muted">{section.rows.length}</span>}>{section.title}</SectionTitle>
          <ul>
            {section.rows.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-3 rounded-xl px-2 py-2 hover:bg-hover/60">
                <Avatar name={row.name} size="lg" />
                <div className="min-w-0 flex-1">
                  <Link href={`/contacts/${row.id}`} className="block truncate text-sm font-medium hover:underline">
                    {row.name}
                  </Link>
                  <div className="truncate text-xs text-muted">
                    {[row.company, frequencyLabel(row.frequency_days), `Последнее: ${lastInteractionText(row)}`].filter(Boolean).join(' · ')}
                  </div>
                </div>
                <DueBadgeView row={row} />
                <RowActions row={row} />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
