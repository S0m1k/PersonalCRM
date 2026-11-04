'use client';

import { useMemo, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { Avatar } from '@/components/app/avatar';
import { Button } from '@/components/ui/button';
import { Card, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { getContacts, type Contact } from '@/lib/api';
import { assignCircles, type CircleSetting, type GoalsState } from '@/lib/api-goals';
import { PRIORITY_LEVELS, PRIORITY_META } from '@/lib/priority';
import { errorText, fullName } from '@/lib/utils';

const PAGE = 200;
const SELECT_CLASS =
  'h-8 rounded-lg border border-line-strong bg-surface px-2 text-[13px] text-fg focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20';

interface Props {
  assignments: GoalsState['assignments'];
  circles: CircleSetting[];
  onSaved: (state: GoalsState) => void;
}

/** Распределение по кругам Данбара без drag-and-drop: список, поиск, фильтр по приоритету, массовое назначение. */
export function CirclesAssigner({ assignments, circles, onSaved }: Props) {
  const [q, setQ] = useState('');
  const [priority, setPriority] = useState('');
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [bulk, setBulk] = useState('1');
  const [busy, setBusy] = useState(false);
  const { data: contacts, isLoading } = useSWR<Contact[]>(['goals-contacts', q, priority], () =>
    getContacts({ q: q || undefined, priority: priority || undefined, limit: PAGE, sort: 'name' }),
  );

  const counts = useMemo(() => {
    const c = [0, 0, 0, 0];
    Object.values(assignments).forEach((a) => { c[a.circle - 1] += 1; });
    return c;
  }, [assignments]);

  async function save(changes: Record<string, number | null>) {
    setBusy(true);
    try {
      onSaved(await assignCircles(changes));
      setPicked(new Set());
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  const toggle = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  const list = contacts ?? [];

  return (
    <Card>
      <CardHeader label="Распределить по кругам" />
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {circles.map((c, i) => (
          <div key={i} className="rounded-xl border border-line px-3 py-1.5 text-sm">
            <span className="text-muted">Круг {i + 1}</span>
            <div className={counts[i] > c.capacity ? 'font-semibold text-danger' : 'font-semibold'}>{counts[i]} / {c.capacity}</div>
          </div>
        ))}
      </div>

      <div className="mb-2 flex flex-wrap gap-2">
        <Input className="h-8 max-w-56" placeholder="Поиск по имени" aria-label="Поиск контактов" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={SELECT_CLASS} aria-label="Фильтр по приоритету" value={priority} onChange={(e) => setPriority(e.target.value)}>
          <option value="">Любой приоритет</option>
          {PRIORITY_LEVELS.map((p) => <option key={p} value={p}>{PRIORITY_META[p].label}</option>)}
        </select>
        <div className="ml-auto flex items-center gap-2">
          <select className={SELECT_CLASS} aria-label="Круг для выбранных" value={bulk} onChange={(e) => setBulk(e.target.value)}>
            {[1, 2, 3, 4].map((n) => <option key={n} value={n}>Круг {n}</option>)}
            <option value="0">Без круга</option>
          </select>
          <Button
            size="sm" variant="primary" disabled={busy || picked.size === 0}
            onClick={() => save(Object.fromEntries([...picked].map((id) => [id, bulk === '0' ? null : Number(bulk)])))}
          >
            Назначить выбранным ({picked.size})
          </Button>
        </div>
      </div>

      {isLoading ? (
        <p className="py-4 text-sm text-muted">Загрузка контактов…</p>
      ) : list.length === 0 ? (
        <p className="py-4 text-sm text-muted">Контактов не найдено.</p>
      ) : (
        <ul className="max-h-96 divide-y divide-line overflow-y-auto rounded-xl border border-line">
          {list.map((c) => {
            const name = fullName(c) || c.company || 'Без имени';
            return (
              <li key={c.id} className="flex items-center gap-3 px-3 py-1.5">
                <input type="checkbox" aria-label={`Выбрать: ${name}`} checked={picked.has(c.id)} onChange={() => toggle(c.id)} />
                <Avatar name={name} size="sm" />
                <span className="min-w-0 flex-1 truncate text-sm">{name}</span>
                <select
                  className={SELECT_CLASS} aria-label={`Круг: ${name}`} disabled={busy}
                  value={assignments[c.id]?.circle ?? 0}
                  onChange={(e) => save({ [c.id]: Number(e.target.value) || null })}
                >
                  <option value={0}>Без круга</option>
                  {[1, 2, 3, 4].map((n) => <option key={n} value={n}>Круг {n}</option>)}
                </select>
              </li>
            );
          })}
        </ul>
      )}
      {list.length >= PAGE && <p className="mt-2 text-xs text-muted">Показаны первые {PAGE}: уточните поиск, чтобы найти остальных.</p>}
    </Card>
  );
}
