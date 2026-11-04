'use client';

import { Suspense, useMemo, useState } from 'react';
import useSWR, { mutate } from 'swr';
import { BellRing } from 'lucide-react';
import { toast } from 'sonner';
import type { Contact } from '@/lib/api';
import {
  groupsKey,
  keepInTouchBoardKey,
  tagsKey,
  type Group,
  type KeepInTouchBuckets,
  type TagCount,
} from '@/lib/api-crm';
import { rowsFromBuckets, setFrequency, withFrequency, type KitRow } from '@/lib/keep-in-touch';
import { errorText } from '@/lib/utils';
import { EmptyState, Page, PageHeader, Skeleton } from '@/components/app/page';
import { KitBoard } from '@/components/keep-in-touch/board';
import { useKitDisplay } from '@/components/keep-in-touch/display';
import { CustomFrequencyDialog } from '@/components/keep-in-touch/kit-bits';
import { KitList } from '@/components/keep-in-touch/list-view';
import { DisplayPopover, FilterMenu, ViewSwitch, type KitView } from '@/components/keep-in-touch/toolbar';
import { KitUpcoming } from '@/components/keep-in-touch/upcoming-view';
import { useUrlState } from '@/components/timeline/use-url-state';

const VIEWS: KitView[] = ['board', 'list', 'upcoming'];
const GROUP_MEMBERS_LIMIT = 200;

function KeepInTouchView() {
  const url = useUrlState();
  const rawView = url.get('view') as KitView;
  const view: KitView = VIEWS.includes(rawView) ? rawView : 'board';
  const groupId = url.get('group');
  const tag = url.get('tag');

  const [display, updateDisplay] = useKitDisplay();
  // Оптимистичные частоты: id → дни (null — снять), пока PATCH в пути
  const [pending, setPending] = useState<Record<string, number | null>>({});
  const [customFor, setCustomFor] = useState<KitRow | null>(null);

  const { data, error, isLoading } = useSWR<KeepInTouchBuckets>(keepInTouchBoardKey());
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());
  const { data: tags = [] } = useSWR<TagCount[]>(tagsKey());
  const { data: members } = useSWR<Contact[]>(groupId ? `/api/contacts/?group_id=${groupId}&limit=${GROUP_MEMBERS_LIMIT}` : null);

  const rows = useMemo(() => {
    const memberIds = groupId && members ? new Set(members.map((m) => m.id)) : null;
    return rowsFromBuckets(data ?? { overdue: [], due_soon: [], upcoming: [], snoozed: [] })
      .filter((r) => (memberIds ? memberIds.has(r.id) : true))
      .filter((r) => (tag ? r.tags.some((t) => t.toLowerCase() === tag.toLowerCase()) : true))
      .filter((r) => display.showSnoozed || r.status !== 'snoozed')
      .map((r) => (r.id in pending ? withFrequency(r, pending[r.id]) : r));
  }, [data, groupId, members, tag, display.showSnoozed, pending]);

  async function move(row: KitRow, days: number | null) {
    setPending((p) => ({ ...p, [row.id]: days }));
    try {
      await setFrequency(row, days);
      await mutate((key) => typeof key === 'string' && key.startsWith('/api/keep-in-touch'));
      await mutate((key) => typeof key === 'string' && key.startsWith('/api/contacts'));
    } catch (err) {
      toast.error(`Не удалось сменить частоту: ${errorText(err)}`);
    } finally {
      setPending(({ [row.id]: _drop, ...rest }) => rest);
    }
  }

  const withFreq = rows.filter((r) => r.status !== 'unset');
  const isEmpty = !isLoading && !error && rows.length === 0;

  return (
    <Page wide>
      <PageHeader
        title="Keep in Touch"
        description="Задайте ритм общения — и CRM напомнит, кому пора написать"
        actions={<DisplayPopover display={display} onChange={updateDisplay} />}
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <ViewSwitch value={view} onChange={(v) => url.set({ view: v === 'board' ? '' : v })} />
        <FilterMenu groups={groups} tags={tags} groupId={groupId} tag={tag} onChange={(patch) => url.set(patch)} />
      </div>

      {error ? (
        <EmptyState icon={BellRing} title="Не удалось загрузить">{errorText(error)}</EmptyState>
      ) : isLoading ? (
        <div className="flex gap-3" aria-busy>
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-64 w-64 shrink-0 rounded-2xl" />
          ))}
        </div>
      ) : isEmpty ? (
        <EmptyState icon={BellRing} title="Здесь пока никого">
          {groupId || tag ? 'В этом фильтре нет контактов.' : 'Добавьте контакты и задайте частоту общения — напоминания появятся здесь.'}
        </EmptyState>
      ) : view === 'board' ? (
        <KitBoard rows={rows} display={display} onMove={(r, d) => void move(r, d)} onPickCustom={setCustomFor} />
      ) : view === 'list' ? (
        <KitList rows={rows} />
      ) : withFreq.length === 0 ? (
        <EmptyState icon={BellRing} title="Нет напоминаний">Задайте частоту общения у контактов — на доске это можно сделать перетаскиванием.</EmptyState>
      ) : (
        <KitUpcoming rows={withFreq} />
      )}

      {customFor && (
        <CustomFrequencyDialog
          row={customFor}
          onClose={() => setCustomFor(null)}
          onSubmit={(days) => {
            void move(customFor, days);
            setCustomFor(null);
          }}
        />
      )}
    </Page>
  );
}

export default function KeepInTouchPage() {
  return (
    <Suspense fallback={null}>
      <KeepInTouchView />
    </Suspense>
  );
}
