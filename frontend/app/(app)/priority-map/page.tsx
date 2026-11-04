'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { toast } from 'sonner';
import { Grid2x2, RotateCcw, Settings2 } from 'lucide-react';
import { Avatar } from '@/components/app/avatar';
import { Page, PageHeader, Skeleton } from '@/components/app/page';
import { PriorityArcs, type PriorityArcsHandle } from '@/components/priority/priority-arcs';
import { PriorityLabelsDialog } from '@/components/priority/priority-labels-dialog';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { Input } from '@/components/ui/input';
import { SectionLabel } from '@/components/ui/section-label';
import { updateContact, type Contact } from '@/lib/api';
import { groupsKey, type Group } from '@/lib/api-crm';
import { priorityLabelsKey, type PriorityLabels } from '@/lib/api-preferences';
import { ALL_CONTACTS_KEY, loadAllContacts } from '@/lib/contacts-all';
import { PRIORITY_LEVELS, PRIORITY_META, priorityLabel, type PriorityLevel } from '@/lib/priority';
import { contactTier, tierAt } from '@/lib/priority-geometry';
import { errorText, fullName, plural } from '@/lib/utils';

const DRAG_SLOP_PX = 4;
const TRAY_LIMIT = 36;
const HIDE_TRAY_KEY = 'priority-map:hide-tray';
const HELP = [
  'Перетащите аватар на дугу — приоритет изменится.',
  'Нажмите на аватар (или Enter), чтобы выбрать уровень из списка или клавишами 1–5.',
  'Колесо мыши — масштаб, перетаскивание фона — сдвиг.',
];

interface DragState {
  id: string;
  startX: number;
  startY: number;
  x: number;
  y: number;
  isActive: boolean;
  tier: PriorityLevel | null;
}

const selectClass = 'h-8 w-full rounded-lg border border-line-strong bg-surface px-2 text-[13px] text-fg';

export default function PriorityMapPage() {
  const arcsRef = useRef<PriorityArcsHandle>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState('');
  const [groupId, setGroupId] = useState('');
  const [isTrayHidden, setIsTrayHidden] = useState(false);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overflowTier, setOverflowTier] = useState<PriorityLevel | null>(null);
  const [isRenaming, setIsRenaming] = useState(false);

  const { data: contacts, isLoading, mutate } = useSWR<Contact[]>(ALL_CONTACTS_KEY, loadAllContacts);
  const { data: groups } = useSWR<Group[]>(groupsKey());
  const { data: labels } = useSWR<PriorityLabels>(priorityLabelsKey());

  useEffect(() => {
    // Сохранённый выбор — из внешнего хранилища, читаем после монтирования
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setIsTrayHidden(localStorage.getItem(HIDE_TRAY_KEY) === '1');
  }, []);

  const shown = useMemo(() => (contacts ?? []).filter((c) => !groupId || c.group_ids.includes(groupId)), [contacts, groupId]);
  const people = useMemo(() => new Map((contacts ?? []).map((c) => [c.id, c])), [contacts]);

  const { tiers, unset } = useMemo(() => {
    const byTier: Record<PriorityLevel, { id: string; name: string }[]> = { top: [], high: [], medium: [], low: [], none: [] };
    const loose: { id: string; name: string }[] = [];
    for (const c of shown) {
      const item = { id: c.id, name: fullName(c) || 'Без имени' };
      const tier = contactTier(c.priority);
      (tier ? byTier[tier] : loose).push(item);
    }
    return { tiers: byTier, unset: loose };
  }, [shown]);

  const highlightId = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return null;
    const all = [...unset, ...PRIORITY_LEVELS.flatMap((t) => tiers[t])];
    return all.find((p) => p.name.toLowerCase().includes(q))?.id ?? null;
  }, [search, tiers, unset]);

  const withPriority = shown.length - unset.length;
  const percent = shown.length ? Math.round((withPriority / shown.length) * 100) : 0;

  async function setPriority(id: string, level: PriorityLevel) {
    const current = people.get(id);
    if (!current || current.priority === level) return;
    const patch = (list?: Contact[]) => list?.map((c) => (c.id === id ? { ...c, priority: level } : c)) ?? [];
    try {
      await mutate(
        async (list) => {
          await updateContact(id, { priority: level });
          return patch(list);
        },
        { optimisticData: (list) => patch(list), rollbackOnError: true, revalidate: false },
      );
    } catch (err) {
      toast.error(`Не удалось изменить приоритет: ${errorText(err)}`);
    }
  }

  // Перетаскивание: одно на дуги и лоток. Слушатели вешаем на window, пока кнопка зажата.
  const dragRef = useRef<DragState | null>(null);
  const dragId = drag?.id;
  useEffect(() => {
    if (!dragId) return;
    const tierUnder = (x: number, y: number): PriorityLevel | null => {
      const frame = frameRef.current?.getBoundingClientRect();
      if (!frame || x < frame.left || x > frame.right || y < frame.top || y > frame.bottom) return null;
      const p = arcsRef.current?.toMap(x, y);
      return p ? tierAt(p.x, p.y) : null;
    };
    const onMove = (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const isActive = d.isActive || Math.hypot(e.clientX - d.startX, e.clientY - d.startY) > DRAG_SLOP_PX;
      const next = { ...d, x: e.clientX, y: e.clientY, isActive, tier: isActive ? tierUnder(e.clientX, e.clientY) : null };
      dragRef.current = next;
      setDrag(next);
    };
    const onUp = (e: PointerEvent) => {
      const d = dragRef.current;
      dragRef.current = null;
      setDrag(null);
      if (!d) return;
      if (!d.isActive) {
        setActiveId(d.id);
        return;
      }
      const tier = tierUnder(e.clientX, e.clientY);
      if (tier) void setPriority(d.id, tier);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
    // setPriority читает свежие данные через mutate; перепривязка на каждый рендер не нужна
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dragId]);

  function startDrag(id: string, e: React.PointerEvent) {
    const next: DragState = { id, startX: e.clientX, startY: e.clientY, x: e.clientX, y: e.clientY, isActive: false, tier: null };
    dragRef.current = next;
    setDrag(next);
  }

  function toggleTray(hidden: boolean) {
    setIsTrayHidden(hidden);
    localStorage.setItem(HIDE_TRAY_KEY, hidden ? '1' : '0');
  }

  const activePerson = activeId ? people.get(activeId) : undefined;
  const draggedPerson = drag?.isActive ? people.get(drag.id) : undefined;
  const overflowPeople = overflowTier ? tiers[overflowTier] : [];

  return (
    <Page wide>
      <PageHeader icon={Grid2x2} title="Priority Map" description="Расставьте людей по кругам близости: чем ближе к центру, тем важнее." />
      {isLoading || !contacts ? (
        <Skeleton className="h-[560px] rounded-2xl" />
      ) : (
        <div className="flex flex-col gap-3">
          <div ref={frameRef} className="relative h-[calc(100vh-360px)] min-h-[520px] overflow-hidden rounded-2xl border border-line bg-surface">
            <PriorityArcs
              ref={arcsRef}
              tiers={tiers}
              labels={labels ?? {}}
              highlightId={highlightId}
              draggingId={drag?.isActive ? drag.id : null}
              dropTier={drag?.tier ?? null}
              onAvatarPointerDown={startDrag}
              onAvatarActivate={setActiveId}
              onOverflow={setOverflowTier}
            />
            <div className="absolute left-3 top-3">
              <Button size="sm" onClick={() => arcsRef.current?.reset()}>
                <RotateCcw aria-hidden />
                Сбросить вид
              </Button>
            </div>
            <aside className="absolute right-3 top-3 z-10 flex max-h-[calc(100%-1.5rem)] w-72 max-w-[calc(100%-1.5rem)] flex-col gap-3 overflow-auto rounded-2xl border border-line bg-surface/95 p-4 shadow-lg backdrop-blur">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="font-display text-xl font-semibold leading-tight">{percent}% с приоритетом</h2>
                  <p className="text-xs text-muted">{withPriority} из {shown.length}</p>
                </div>
                <Button variant="ghost" size="icon" aria-label="Переименовать уровни" onClick={() => setIsRenaming(true)}>
                  <Settings2 />
                </Button>
              </div>
              <Input aria-label="Найти контакт" placeholder="Найти контакт" value={search} onChange={(e) => setSearch(e.target.value)} className="h-8" />
              <select aria-label="Группа" className={selectClass} value={groupId} onChange={(e) => setGroupId(e.target.value)}>
                <option value="">Все группы</option>
                {groups?.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
              <div>
                <SectionLabel>Уровни</SectionLabel>
                <ul className="mt-1.5 space-y-1.5">
                  {[...PRIORITY_LEVELS.map((t) => ({ key: t as string, label: priorityLabel(t, labels), count: tiers[t].length })), { key: 'unset', label: 'Не задан', count: unset.length }].map((row) => (
                    <li key={row.key} className="text-xs">
                      <div className="flex justify-between"><span>{row.label}</span><span className="text-muted">{row.count}</span></div>
                      <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-hover">
                        <div className="h-full rounded-full bg-accent" style={{ width: `${shown.length ? (row.count / shown.length) * 100 : 0}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <SectionLabel>Как пользоваться</SectionLabel>
                <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-muted">{HELP.map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            </aside>
          </div>

          {!isTrayHidden ? (
            <section aria-label="Контакты без приоритета" className="rounded-2xl border border-line bg-surface p-3">
              <div className="mb-2 flex items-center justify-between gap-2">
                <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Без приоритета {unset.length}</div>
                <div className="flex gap-1.5">
                  <Button size="sm" asChild><Link href="/contacts/quick-action">Расставить приоритеты</Link></Button>
                  <Button size="sm" variant="ghost" onClick={() => toggleTray(true)}>Скрыть</Button>
                </div>
              </div>
              {unset.length === 0 ? (
                <p className="text-sm text-muted">У всех контактов есть приоритет.</p>
              ) : (
                <ul className="flex flex-wrap gap-1.5">
                  {unset.slice(0, TRAY_LIMIT).map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        title={p.name}
                        aria-label={`${p.name}: выбрать приоритет`}
                        className="touch-none rounded-full"
                        onPointerDown={(e) => startDrag(p.id, e)}
                        onKeyDown={(e) => e.key === 'Enter' && setActiveId(p.id)}
                      >
                        <Avatar name={p.name} size="lg" />
                      </button>
                    </li>
                  ))}
                  {unset.length > TRAY_LIMIT && <li className="grid h-9 place-items-center rounded-full bg-hover px-2.5 text-xs text-muted">+{unset.length - TRAY_LIMIT}</li>}
                </ul>
              )}
            </section>
          ) : (
            <div><Button size="sm" variant="ghost" onClick={() => toggleTray(false)}>Показать «Без приоритета» ({unset.length})</Button></div>
          )}
        </div>
      )}

      {draggedPerson && drag && (
        <div className="pointer-events-none fixed z-50 -translate-x-1/2 -translate-y-1/2 opacity-90" style={{ left: drag.x, top: drag.y }}>
          <Avatar name={fullName(draggedPerson) || '?'} size="lg" className="shadow-lg ring-2 ring-accent" />
        </div>
      )}

      <Dialog open={!!activePerson} onOpenChange={(open) => !open && setActiveId(null)}>
        <DialogContent title={activePerson ? fullName(activePerson) || 'Без имени' : ''} description="Выберите уровень приоритета">
          <div
            className="space-y-1.5"
            onKeyDown={(e) => {
              const level = PRIORITY_LEVELS.find((t) => PRIORITY_META[t].hotkey === e.key);
              if (level && activePerson) {
                void setPriority(activePerson.id, level);
                setActiveId(null);
              }
            }}
          >
            {PRIORITY_LEVELS.map((level) => (
              <Button
                key={level}
                variant={activePerson?.priority === level ? 'primary' : 'outline'}
                className="w-full justify-between"
                onClick={() => {
                  if (activePerson) void setPriority(activePerson.id, level);
                  setActiveId(null);
                }}
              >
                {priorityLabel(level, labels)}
                <kbd className="text-[11px] opacity-60">{PRIORITY_META[level].hotkey}</kbd>
              </Button>
            ))}
            {activePerson && <Button variant="ghost" className="w-full" asChild><Link href={`/contacts/${activePerson.id}`}>Открыть карточку</Link></Button>}
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={overflowTier !== null} onOpenChange={(open) => !open && setOverflowTier(null)}>
        <DialogContent title={overflowTier ? `${priorityLabel(overflowTier, labels)} · ${overflowPeople.length} ${plural(overflowPeople.length, 'контакт', 'контакта', 'контактов')}` : ''}>
          <ul className="max-h-80 overflow-auto">
            {overflowPeople.map((p) => (
              <li key={p.id}>
                <button type="button" className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left hover:bg-hover" onClick={() => { setOverflowTier(null); setActiveId(p.id); }}>
                  <Avatar name={p.name} />
                  <span className="truncate text-sm">{p.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>

      <PriorityLabelsDialog open={isRenaming} onOpenChange={setIsRenaming} labels={labels} />
    </Page>
  );
}
