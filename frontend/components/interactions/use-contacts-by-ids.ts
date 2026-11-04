import useSWR from 'swr';
import { getContact } from '@/lib/api';
import { fullName } from '@/lib/utils';
import type { PickedContact } from '@/components/calendar/contact-picker';

/** Имена контактов по id (кэшируется SWR); не найденные пропускаются. */
export function useContactsByIds(ids: string[]): PickedContact[] {
  const key = ids.length > 0 ? ['contacts-by-ids', ...ids] : null;
  const { data } = useSWR<PickedContact[]>(key, async () => {
    const found = await Promise.all(ids.map((id) => getContact(id).catch(() => null)));
    return found.flatMap((c) => (c ? [{ id: c.id, name: fullName(c) || 'Без имени' }] : []));
  });
  return data ?? [];
}
