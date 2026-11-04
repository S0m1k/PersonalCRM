import { mutate } from 'swr';

/** Обновить всё, что зависит от взаимодействий: ленты, контакты (last_interaction_at), Keep in touch, главную. */
export function revalidateInteractions(): Promise<unknown[]> {
  return Promise.all([
    mutate((key) => typeof key === 'string' && key.startsWith('/api/interactions')),
    mutate((key) => typeof key === 'string' && key.startsWith('/api/keep-in-touch')),
    mutate((key) => typeof key === 'string' && key.startsWith('/api/contacts')),
    mutate('/api/home'),
  ]);
}
