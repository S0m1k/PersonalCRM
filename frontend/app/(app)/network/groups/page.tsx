'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { Users } from 'lucide-react';
import { Avatar } from '@/components/app/avatar';
import { EmptyState, Skeleton } from '@/components/app/page';
import { GraphCanvas, type GNode } from '@/components/network/graph-canvas';
import { NetworkPanel } from '@/components/network/network-panel';
import { useNetwork } from '@/components/network/use-network';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from '@/components/ui/overlays';
import { createGroup, groupsKey, type Group } from '@/lib/api-crm';
import { avatarToken } from '@/lib/css-color';
import { radialLayout, type Hub } from '@/lib/network-layout';
import { errorText, plural } from '@/lib/utils';

const GROUP_RADIUS = 26;
const TRAY_LIMIT = 40;
const HELP = [
  'Перетащите контакт на группу — он добавится в неё.',
  'Или нажмите на аватар в лотке «Без группы» и выберите «Добавить в группу».',
  'Нажмите на контакт, чтобы открыть карточку.',
];

export default function GroupsNetworkPage() {
  const router = useRouter();
  const { mutate: mutateGlobal } = useSWRConfig();
  const { graph, isLoading, setGroups } = useNetwork();
  const { data: groups } = useSWR<Group[]>(groupsKey());
  const [search, setSearch] = useState('');
  const [newName, setNewName] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  const members = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.id, n])), [graph]);
  const ungrouped = useMemo(() => (graph?.nodes ?? []).filter((n) => n.group_ids.length === 0), [graph]);

  const layout = useMemo(() => {
    const hubs: Hub[] = (groups ?? []).map((g) => ({
      id: `group:${g.id}`,
      label: g.name,
      token: avatarToken(g.name),
      r: GROUP_RADIUS,
      members: (graph?.nodes ?? []).filter((n) => n.group_ids.includes(g.id)),
    }));
    return radialLayout(hubs, 'group');
  }, [groups, graph]);

  const highlightId = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? (layout.nodes.find((n) => n.kind === 'contact' && n.label.toLowerCase().includes(q))?.id ?? null) : null;
  }, [layout, search]);

  async function addToGroup(contactId: string, groupId: string) {
    const current = members.get(contactId);
    if (!current || current.group_ids.includes(groupId)) return;
    try {
      await setGroups(contactId, [...current.group_ids, groupId]);
      void mutateGlobal(groupsKey());
      toast.success('Добавлено в группу');
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setIsCreating(true);
    try {
      await createGroup({ name });
      setNewName('');
      await mutateGlobal(groupsKey());
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsCreating(false);
    }
  }

  function handleDrop(dragged: GNode, target: GNode) {
    if (target.kind === 'group' && dragged.kind === 'contact') void addToGroup(dragged.id, target.id.replace('group:', ''));
  }

  if (isLoading || !graph || !groups) return <Skeleton className="h-[560px] rounded-2xl" />;
  if (graph.nodes.length === 0) {
    return <EmptyState icon={Users} title="Контактов пока нет">Добавьте людей, и здесь появится граф групп.</EmptyState>;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative h-[calc(100vh-380px)] min-h-[440px] overflow-hidden rounded-2xl border border-line bg-surface">
        <GraphCanvas
          nodes={layout.nodes}
          links={layout.links}
          highlightId={highlightId}
          isDraggable={(n) => n.kind === 'contact'}
          onNodeClick={(n) => n.kind === 'contact' && router.push(`/contacts/${n.id}`)}
          onNodeDrop={handleDrop}
          onExternalDrop={(target, data) => {
            if (target?.kind === 'group' && data) void addToGroup(data, target.id.replace('group:', ''));
          }}
          ariaLabel="Граф групп: «Я» в центре, группы вокруг, контакты у своих групп"
          className="size-full"
        />
        <NetworkPanel
          title="Группы"
          subtitle={`${groups.length} ${plural(groups.length, 'группа', 'группы', 'групп')} · ${graph.nodes.length} ${plural(graph.nodes.length, 'контакт', 'контакта', 'контактов')}`}
          search={{ value: search, onChange: setSearch, placeholder: 'Найти контакт' }}
          help={HELP}
        >
          <form onSubmit={handleCreate} className="flex gap-1.5">
            <Input aria-label="Название новой группы" placeholder="Добавить группу" value={newName} onChange={(e) => setNewName(e.target.value)} maxLength={80} className="h-8" />
            <Button type="submit" size="sm" variant="primary" disabled={isCreating || !newName.trim()}>ОК</Button>
          </form>
        </NetworkPanel>
      </div>

      <section aria-label="Контакты без группы" className="rounded-2xl border border-line bg-surface p-3">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Без группы {ungrouped.length}</div>
        {ungrouped.length === 0 ? (
          <p className="text-sm text-muted">Все контакты разложены по группам.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {ungrouped.slice(0, TRAY_LIMIT).map((c) => (
              <li key={c.id}>
                <Menu>
                  <MenuTrigger asChild>
                    <button
                      type="button"
                      draggable
                      onDragStart={(e) => e.dataTransfer.setData('text/plain', c.id)}
                      title={c.name}
                      aria-label={`${c.name}: добавить в группу`}
                      className="rounded-full"
                    >
                      <Avatar name={c.name} size="lg" />
                    </button>
                  </MenuTrigger>
                  <MenuContent>
                    <MenuLabel>Добавить в группу…</MenuLabel>
                    {groups.length === 0 && <div className="px-2 py-1.5 text-sm text-muted">Сначала создайте группу</div>}
                    {groups.map((g) => (
                      <MenuItem key={g.id} onSelect={() => void addToGroup(c.id, g.id)}>{g.name}</MenuItem>
                    ))}
                    <MenuItem onSelect={() => router.push(`/contacts/${c.id}`)}>Открыть карточку</MenuItem>
                  </MenuContent>
                </Menu>
              </li>
            ))}
            {ungrouped.length > TRAY_LIMIT && (
              <li className="grid h-9 place-items-center rounded-full bg-hover px-2.5 text-xs text-muted">+{ungrouped.length - TRAY_LIMIT}</li>
            )}
          </ul>
        )}
      </section>
    </div>
  );
}
