'use client';

import { useCallback } from 'react';
import { useSWRConfig } from 'swr';

/** Всё, что зависит от взаимодействий: ленты, контакты (last_interaction_at), Keep in touch, главная. */
const AFFECTED_PREFIXES = ['/api/interactions', '/api/keep-in-touch', '/api/contacts', '/api/home'];

/**
 * Функция «обновить всё, что зависит от взаимодействий».
 *
 * Именно хук: у приложения свой кэш SWR (provider в app-shell), а глобальный `mutate` из 'swr'
 * работает с другим, пустым кэшем и ничего не обновляет — экран оставался бы устаревшим.
 */
export function useRevalidateInteractions(): () => Promise<unknown[]> {
  const { mutate } = useSWRConfig();
  return useCallback(
    () => mutate((key) => typeof key === 'string' && AFFECTED_PREFIXES.some((prefix) => key.startsWith(prefix))),
    [mutate],
  );
}
