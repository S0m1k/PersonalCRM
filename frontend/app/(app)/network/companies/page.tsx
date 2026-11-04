'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Building2 } from 'lucide-react';
import { EmptyState, Skeleton } from '@/components/app/page';
import { GraphCanvas } from '@/components/network/graph-canvas';
import { NetworkPanel } from '@/components/network/network-panel';
import { useNetwork } from '@/components/network/use-network';
import type { NetworkNode } from '@/lib/api-crm';
import { avatarToken } from '@/lib/css-color';
import { companyRadius, radialLayout, type Hub } from '@/lib/network-layout';
import { plural } from '@/lib/utils';

const MAX_COMPANIES = 60;
const NO_COMPANY_ID = 'company:__none__';
const HELP = [
  'Размер компании — число людей, которые в ней работают.',
  'Нажмите на человека, чтобы открыть карточку.',
  'Колесо мыши — масштаб, перетаскивание фона — сдвиг.',
];

export default function CompaniesNetworkPage() {
  const router = useRouter();
  const { graph, isLoading } = useNetwork();
  const [search, setSearch] = useState('');
  const [isShowingLoners, setIsShowingLoners] = useState(false);

  const { hubs, withoutCompany } = useMemo(() => {
    const byCompany = new Map<string, { label: string; members: NetworkNode[] }>();
    const loners: NetworkNode[] = [];
    for (const node of graph?.nodes ?? []) {
      const label = node.company.trim().replace(/\s+/g, ' ');
      if (!label) {
        loners.push(node);
        continue;
      }
      const entry = byCompany.get(label.toLowerCase()) ?? { label, members: [] };
      entry.members.push(node);
      byCompany.set(label.toLowerCase(), entry);
    }
    const list: Hub[] = [...byCompany.entries()]
      .sort((a, b) => b[1].members.length - a[1].members.length)
      .slice(0, MAX_COMPANIES)
      .map(([key, entry]) => ({
        id: `company:${key}`,
        label: entry.label,
        token: avatarToken(entry.label),
        r: companyRadius(entry.members.length),
        members: entry.members,
      }));
    return { hubs: list, withoutCompany: loners };
  }, [graph]);

  const layout = useMemo(() => {
    const all = isShowingLoners && withoutCompany.length
      ? [...hubs, { id: NO_COMPANY_ID, label: 'Без компании', token: 'tag-gray', r: companyRadius(withoutCompany.length), members: withoutCompany }]
      : hubs;
    return radialLayout(all, 'company');
  }, [hubs, withoutCompany, isShowingLoners]);

  const highlightId = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? (layout.nodes.find((n) => n.label.toLowerCase().includes(q) && n.kind !== 'me')?.id ?? null) : null;
  }, [layout, search]);

  if (isLoading || !graph) return <Skeleton className="h-[560px] rounded-2xl" />;
  if (hubs.length === 0) {
    return (
      <EmptyState icon={Building2} title="Компании не указаны">
        Заполните поле «Компания» у контактов, и здесь появится граф компаний.
      </EmptyState>
    );
  }

  return (
    <div className="relative h-[calc(100vh-300px)] min-h-[520px] overflow-hidden rounded-2xl border border-line bg-surface">
      <GraphCanvas
        nodes={layout.nodes}
        links={layout.links}
        highlightId={highlightId}
        onNodeClick={(n) => n.kind === 'contact' && router.push(`/contacts/${n.id}`)}
        ariaLabel="Граф компаний: «Я» в центре, компании вокруг, сотрудники у своих компаний"
        className="size-full"
      />
      <NetworkPanel
        title="Компании"
        subtitle={`${hubs.length} ${plural(hubs.length, 'компания', 'компании', 'компаний')} · ${(graph.nodes.length - withoutCompany.length)} ${plural(graph.nodes.length - withoutCompany.length, 'человек', 'человека', 'человек')}`}
        search={{ value: search, onChange: setSearch, placeholder: 'Найти компанию или человека' }}
        help={HELP}
      >
        {withoutCompany.length > 0 && (
          <label className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" checked={isShowingLoners} onChange={(e) => setIsShowingLoners(e.target.checked)} className="size-4 accent-[rgb(var(--accent))]" />
            Показать без компании {withoutCompany.length}
          </label>
        )}
      </NetworkPanel>
    </div>
  );
}
