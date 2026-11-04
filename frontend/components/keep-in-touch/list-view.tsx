'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { frequencyLabel } from '@/lib/frequency';
import type { KitRow } from '@/lib/keep-in-touch';
import { formatDate } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { DueBadgeView, lastInteractionText } from './kit-bits';
import { RowActions } from './row-actions';

/** Без срока (нет частоты) — в конец при любом порядке. */
function compareDue(a: KitRow, b: KitRow, dir: 1 | -1): number {
  if (!a.due_date && !b.due_date) return a.name.localeCompare(b.name, 'ru');
  if (!a.due_date) return 1;
  if (!b.due_date) return -1;
  return dir * a.due_date.localeCompare(b.due_date) || a.name.localeCompare(b.name, 'ru');
}

/** Таблица контактов: сортировка по сроку, быстрые действия в строке. */
export function KitList({ rows }: { rows: KitRow[] }) {
  const [dir, setDir] = useState<1 | -1>(1);
  const sorted = useMemo(() => [...rows].sort((a, b) => compareDue(a, b, dir)), [rows, dir]);

  if (rows.length === 0) return null;
  return (
    <div className="overflow-x-auto rounded-2xl border border-line">
      <table className="w-full min-w-[820px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
            <th scope="col" className="px-3 py-2.5">Контакт</th>
            <th scope="col" className="px-3 py-2.5">Частота</th>
            <th scope="col" className="px-3 py-2.5">Последнее общение</th>
            <th scope="col" className="px-3 py-2.5" aria-sort={dir === 1 ? 'ascending' : 'descending'}>
              <button type="button" onClick={() => setDir((d) => (d === 1 ? -1 : 1))} className="inline-flex items-center gap-1 uppercase hover:text-fg">
                Срок {dir === 1 ? <ArrowUp className="size-3" aria-hidden /> : <ArrowDown className="size-3" aria-hidden />}
              </button>
            </th>
            <th scope="col" className="px-3 py-2.5">Статус</th>
            <th scope="col" className="px-3 py-2.5"><span className="sr-only">Действия</span></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.id} className="border-b border-line last:border-0 hover:bg-hover/50">
              <td className="px-3 py-2">
                <Link href={`/contacts/${row.id}`} className="flex items-center gap-2 hover:underline">
                  <Avatar name={row.name} size="md" />
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{row.name}</span>
                    {row.company && <span className="block truncate text-xs text-muted">{row.company}</span>}
                  </span>
                </Link>
              </td>
              <td className="px-3 py-2 text-muted">{frequencyLabel(row.frequency_days)}</td>
              <td className="px-3 py-2 text-muted">{lastInteractionText(row)}</td>
              <td className="px-3 py-2 text-muted">{row.due_date ? formatDate(row.due_date, false) : '—'}</td>
              <td className="px-3 py-2">
                <DueBadgeView row={row} />
              </td>
              <td className="px-3 py-2">
                {row.status !== 'unset' ? <RowActions row={row} /> : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
