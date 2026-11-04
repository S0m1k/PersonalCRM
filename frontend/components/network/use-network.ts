'use client';

import useSWR from 'swr';
import { updateContact, getContact } from '@/lib/api';
import { networkKey, type NetworkGraph } from '@/lib/api-crm';

const EMPTY: NetworkGraph = { nodes: [], edges: [], truncated: false };

/** Граф сети + оптимистичные правки узлов (откат при ошибке). */
export function useNetwork(minWeight = 1) {
  const key = networkKey(minWeight);
  const { data, isLoading, mutate } = useSWR<NetworkGraph>(key);

  /** Выставить группы контакту: сразу в интерфейсе, при ошибке вернуть и пробросить её. */
  async function setGroups(contactId: string, groupIds: string[]) {
    const patch = (graph?: NetworkGraph): NetworkGraph | undefined =>
      graph && { ...graph, nodes: graph.nodes.map((n) => (n.id === contactId ? { ...n, group_ids: groupIds } : n)) };
    await mutate(
      async (current) => {
        await updateContact(contactId, { group_ids: groupIds });
        return patch(current);
      },
      { optimisticData: (current) => patch(current) ?? EMPTY, rollbackOnError: true, revalidate: false },
    );
  }

  /** Связать двух людей: добавляет связь в карточку первого (сохраняя остальные). */
  async function link(sourceId: string, targetId: string, label: string) {
    const source = await getContact(sourceId);
    if (source.relationships.some((r) => r.contact_id === targetId)) {
      await updateContact(sourceId, {
        relationships: source.relationships.map((r) => (r.contact_id === targetId ? { ...r, label } : r)),
      });
    } else {
      await updateContact(sourceId, { relationships: [...source.relationships, { contact_id: targetId, label }] });
    }
    await mutate();
  }

  return { graph: data, isLoading, setGroups, link, reload: mutate };
}
