'use client';

import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import type { TableBlock } from '@/lib/api-assistant';
import { SectionLabel } from '@/components/ui/section-label';

type Sort = { key: string; direction: 'asc' | 'desc' } | null;
type Cell = string | number | null | undefined;

/** Числа сравниваем как числа, пустые значения — всегда в конце. */
function compare(a: Cell, b: Cell): number {
  if (a == null || a === '') return b == null || b === '' ? 0 : 1;
  if (b == null || b === '') return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'ru');
}

/** Таблица с сортировкой по клику на заголовок колонки. */
export function TableBlockView({ block }: { block: TableBlock }) {
  const [sort, setSort] = useState<Sort>(null);

  const rows = useMemo(() => {
    if (!sort) return block.rows;
    const sign = sort.direction === 'asc' ? 1 : -1;
    return [...block.rows].sort((a, b) => {
      const empty = (v: Cell) => v == null || v === '';
      // пустые не переворачиваем вместе с направлением
      if (empty(a[sort.key]) || empty(b[sort.key])) return compare(a[sort.key], b[sort.key]);
      return sign * compare(a[sort.key], b[sort.key]);
    });
  }, [block.rows, sort]);

  function toggle(key: string) {
    setSort((current) => {
      if (current?.key !== key) return { key, direction: 'asc' };
      return current.direction === 'asc' ? { key, direction: 'desc' } : null;
    });
  }

  return (
    <div className="overflow-hidden rounded-xl border border-line">
      {block.title && (
        <div className="border-b border-line bg-surface px-3 py-2">
          <SectionLabel>{block.title}</SectionLabel>
        </div>
      )}
      <div className="max-h-96 overflow-auto">
        <table className="w-full text-left text-sm">
          <thead className="sticky top-0 bg-sidebar text-muted">
            <tr>
              {block.columns.map((col) => {
                const active = sort?.key === col.key;
                return (
                  <th
                    key={col.key}
                    scope="col"
                    aria-sort={active ? (sort.direction === 'asc' ? 'ascending' : 'descending') : 'none'}
                    className="px-3 py-1.5 font-medium"
                  >
                    <button
                      type="button"
                      onClick={() => toggle(col.key)}
                      className="inline-flex items-center gap-1 hover:text-fg"
                    >
                      {col.label}
                      {active && (sort.direction === 'asc' ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-line">
                {block.columns.map((col) => (
                  <td key={col.key} className="px-3 py-1.5">
                    {row[col.key] ?? '—'}
                  </td>
                ))}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={block.columns.length} className="px-3 py-3 text-faint">
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
