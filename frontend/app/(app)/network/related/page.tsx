'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Link2, Share2 } from 'lucide-react';
import { EmptyState, Skeleton } from '@/components/app/page';
import { GraphCanvas, type GLink } from '@/components/network/graph-canvas';
import { NetworkPanel } from '@/components/network/network-panel';
import { useNetwork } from '@/components/network/use-network';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { contactNode } from '@/lib/network-layout';
import { errorText, plural } from '@/lib/utils';

const MAX_MIN_WEIGHT = 10;
const MAX_TOGETHER_WIDTH = 5;
const HELP = [
  'Сплошная линия — связь из карточки, пунктир — вы встречались вместе (толще — чаще).',
  'Перетащите контакт на другой, чтобы связать их.',
  'Ползунок скрывает редкие совместные встречи.',
];

const selectClass = 'h-9 w-full rounded-lg border border-line-strong bg-surface px-2 text-sm';

interface LinkDraft {
  sourceId: string;
  targetId: string;
  label: string;
}

export default function RelatedNetworkPage() {
  const router = useRouter();
  const [minWeight, setMinWeight] = useState(1);
  const { graph, isLoading, link } = useNetwork(minWeight);
  const [search, setSearch] = useState('');
  const [draft, setDraft] = useState<LinkDraft | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const { nodes, links, isolated } = useMemo(() => {
    const edges: GLink[] = (graph?.edges ?? []).map((e) =>
      e.kind === 'relationship'
        ? { source: e.source, target: e.target, width: 2.2, label: e.label }
        : { source: e.source, target: e.target, dashed: true, width: Math.min(MAX_TOGETHER_WIDTH, 1 + Math.log2(e.weight + 1)) },
    );
    const connected = new Set(edges.flatMap((e) => [e.source, e.target]));
    const list = (graph?.nodes ?? []).filter((n) => connected.has(n.id)).map((n) => contactNode(n));
    return { nodes: list, links: edges, isolated: (graph?.nodes.length ?? 0) - list.length };
  }, [graph]);

  const highlightId = useMemo(() => {
    const q = search.trim().toLowerCase();
    return q ? (nodes.find((n) => n.label.toLowerCase().includes(q))?.id ?? null) : null;
  }, [nodes, search]);

  async function save() {
    if (!draft || draft.sourceId === draft.targetId || !draft.sourceId || !draft.targetId) return;
    setIsSaving(true);
    try {
      await link(draft.sourceId, draft.targetId, draft.label.trim());
      toast.success('Связь сохранена');
      setDraft(null);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading || !graph) return <Skeleton className="h-[560px] rounded-2xl" />;
  const sorted = [...graph.nodes].sort((a, b) => a.name.localeCompare(b.name, 'ru'));

  return (
    <div className="relative h-[calc(100vh-300px)] min-h-[520px] overflow-hidden rounded-2xl border border-line bg-surface">
      {nodes.length === 0 ? (
        <div className="grid size-full place-items-center p-6">
          <EmptyState icon={Share2} title="Связей пока нет">
            Свяжите людей в карточке или перетащите один контакт на другой — они появятся здесь.
            <div className="mt-3">
              <Button size="sm" onClick={() => setDraft({ sourceId: '', targetId: '', label: '' })}>Связать контакты…</Button>
            </div>
          </EmptyState>
        </div>
      ) : (
        <>
          <GraphCanvas
            nodes={nodes}
            links={links}
            physics
            snapBack={false}
            highlightId={highlightId}
            isDraggable={() => true}
            onNodeClick={(n) => router.push(`/contacts/${n.id}`)}
            onNodeDrop={(a, b) => setDraft({ sourceId: a.id, targetId: b.id, label: '' })}
            ariaLabel="Граф связей между контактами"
            className="size-full"
          />
          <NetworkPanel
            title="Связи"
            subtitle={`${nodes.length} ${plural(nodes.length, 'контакт', 'контакта', 'контактов')} · ${links.length} ${plural(links.length, 'связь', 'связи', 'связей')}${isolated ? ` · без связей ${isolated}` : ''}`}
            search={{ value: search, onChange: setSearch, placeholder: 'Найти контакт' }}
            help={HELP}
          >
            <label className="block text-xs text-muted">
              Минимум совместных встреч: {minWeight}
              <input type="range" min={1} max={MAX_MIN_WEIGHT} value={minWeight} onChange={(e) => setMinWeight(Number(e.target.value))} className="mt-1 w-full accent-[rgb(var(--accent))]" />
            </label>
            <Button size="sm" onClick={() => setDraft({ sourceId: '', targetId: '', label: '' })}>
              <Link2 aria-hidden />
              Связать контакты…
            </Button>
          </NetworkPanel>
        </>
      )}

      <Dialog open={draft !== null} onOpenChange={(open) => !open && setDraft(null)}>
        <DialogContent title="Связать контакты" description="Связь сохранится в карточке первого контакта.">
          {draft && (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
            >
              <label className="block text-sm">
                Кто
                <select className={selectClass} value={draft.sourceId} onChange={(e) => setDraft({ ...draft, sourceId: e.target.value })}>
                  <option value="">Выберите…</option>
                  {sorted.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
                </select>
              </label>
              <label className="block text-sm">
                С кем
                <select className={selectClass} value={draft.targetId} onChange={(e) => setDraft({ ...draft, targetId: e.target.value })}>
                  <option value="">Выберите…</option>
                  {sorted.filter((n) => n.id !== draft.sourceId).map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
                </select>
              </label>
              <label className="block text-sm">
                Кем приходятся (например, «брат», «коллега»)
                <Input value={draft.label} maxLength={80} onChange={(e) => setDraft({ ...draft, label: e.target.value })} autoFocus />
              </label>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="ghost" onClick={() => setDraft(null)}>Отмена</Button>
                <Button type="submit" variant="primary" disabled={isSaving || !draft.sourceId || !draft.targetId || draft.sourceId === draft.targetId}>
                  Сохранить
                </Button>
              </div>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
