'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { Sparkles } from 'lucide-react';
import { EmptyState, Skeleton } from '@/components/app/page';
import { GraphCanvas, type GLink, type GNode } from '@/components/network/graph-canvas';
import { NetworkPanel } from '@/components/network/network-panel';
import { networkKey, type NetworkGraph } from '@/lib/api-crm';
import { universeKey, type Universe } from '@/lib/api-network';
import { avatarToken } from '@/lib/css-color';
import { plural } from '@/lib/utils';

const WORLD_SCALE = 380;
const STAR_RADIUS = 9;
const NO_LINKS: GLink[] = [];
const CLUSTER_TOKENS = ['tag-blue', 'tag-yellow', 'tag-pink', 'tag-green', 'tag-orange', 'tag-purple', 'tag-red', 'tag-brown'];

const HELP = [
  'Каждый контакт — звезда; близкие по профилю (должность, компания, теги) собраны в созвездия.',
  'Колесо мыши — масштаб, перетаскивание фона — сдвиг.',
  'Нажмите на звезду, чтобы открыть карточку.',
];

export default function UniversePage() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const { data: universe, isLoading } = useSWR<Universe>(universeKey());
  const { data: graph } = useSWR<NetworkGraph>(networkKey());

  const { nodes, labels } = useMemo(() => {
    const names = new Map((graph?.nodes ?? []).map((n) => [n.id, n.name]));
    const list: GNode[] = [];
    const labelNodes: GNode[] = [];
    universe?.clusters.forEach((cluster, index) => {
      const members = cluster.contact_ids.filter((id) => names.has(id) && universe.positions[id]);
      if (members.length === 0) return;
      let cx = 0;
      let cy = 0;
      let top = Infinity;
      for (const id of members) {
        const p = universe.positions[id];
        cx += p.x;
        cy += p.y;
        top = Math.min(top, p.y);
        list.push({
          id,
          label: names.get(id) ?? '',
          kind: 'contact',
          r: STAR_RADIUS,
          token: CLUSTER_TOKENS[index % CLUSTER_TOKENS.length] ?? avatarToken(id),
          x: p.x * WORLD_SCALE,
          y: p.y * WORLD_SCALE,
        });
      }
      labelNodes.push({
        id: `cluster-${cluster.id}`,
        label: cluster.label,
        kind: 'label',
        r: 1,
        token: 'surface',
        x: (cx / members.length) * WORLD_SCALE,
        y: top * WORLD_SCALE - 34,
      });
    });
    return { nodes: [...list, ...labelNodes], labels: labelNodes };
  }, [universe, graph]);

  const highlightId = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? (nodes.find((n) => n.kind === 'contact' && n.label.toLowerCase().includes(q))?.id ?? null) : null;
  }, [nodes, search]);

  if (isLoading || !universe) return <Skeleton className="h-[560px] rounded-2xl" />;

  if (!universe.ready) {
    return (
      <EmptyState icon={Sparkles} title="Постройте свою вселенную">
        Здесь контакты складываются в созвездия по сходству профилей. Нужно минимум {universe.required} контактов с
        должностью, компанией, тегами или описанием — сейчас {universe.profiled}.
      </EmptyState>
    );
  }

  const starCount = nodes.length - labels.length;

  return (
    <div className="relative h-[calc(100vh-300px)] min-h-[520px] overflow-hidden rounded-2xl border border-line bg-fg">
      <GraphCanvas
        nodes={nodes}
        links={NO_LINKS}
        isStarfield
        highlightId={highlightId}
        onNodeClick={(n) => router.push(`/contacts/${n.id}`)}
        ariaLabel="Вселенная контактов: звёзды сгруппированы по сходству профилей"
        className="size-full"
      />
      <NetworkPanel
        title="Вселенная"
        subtitle={`${starCount} ${plural(starCount, 'звезда', 'звезды', 'звёзд')} · ${labels.length} ${plural(labels.length, 'созвездие', 'созвездия', 'созвездий')}`}
        search={{ value: search, onChange: setSearch, placeholder: 'Найти контакт' }}
        help={HELP}
      >
        <ul className="space-y-1 text-sm">
          {labels.map((l, i) => (
            <li key={l.id} className="flex items-center gap-2">
              <span className="size-2.5 rounded-full" style={{ background: `rgb(var(--${CLUSTER_TOKENS[i % CLUSTER_TOKENS.length]}))` }} aria-hidden />
              <span className="truncate">{l.label}</span>
            </li>
          ))}
        </ul>
      </NetworkPanel>
    </div>
  );
}
