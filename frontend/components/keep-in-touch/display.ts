'use client';

import { useCallback, useState } from 'react';
import { FREQUENCY_PRESETS } from '@/lib/frequency';
import { CUSTOM_COLUMN, UNSET_COLUMN } from '@/lib/keep-in-touch';

export interface KitDisplay {
  /** id скрытых колонок доски */
  hiddenColumns: string[];
  showSnoozed: boolean;
  compact: boolean;
}

const STORAGE_KEY = 'kit.display';
const DEFAULT_DISPLAY: KitDisplay = { hiddenColumns: [], showSnoozed: true, compact: false };

export interface KitColumn {
  id: string;
  label: string;
  /** days для пресетов; null — «Без частоты»; undefined — своя */
  days: number | null | undefined;
}

export const KIT_COLUMNS: KitColumn[] = [
  { id: UNSET_COLUMN, label: 'Без частоты', days: null },
  ...FREQUENCY_PRESETS.map((p) => ({ id: String(p.days), label: p.label as string, days: p.days as number })),
  { id: CUSTOM_COLUMN, label: 'Своя частота', days: undefined },
];

function load(): KitDisplay {
  if (typeof window === 'undefined') return DEFAULT_DISPLAY;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_DISPLAY, ...(JSON.parse(raw) as Partial<KitDisplay>) } : DEFAULT_DISPLAY;
  } catch {
    return DEFAULT_DISPLAY;
  }
}

/** Настройки отображения Keep in Touch; хранятся в localStorage. */
export function useKitDisplay(): [KitDisplay, (patch: Partial<KitDisplay>) => void] {
  const [display, setDisplay] = useState<KitDisplay>(load);
  const update = useCallback((patch: Partial<KitDisplay>) => {
    setDisplay((prev) => {
      const next = { ...prev, ...patch };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      } catch {
        /* хранилище недоступно — настройки живут до перезагрузки */
      }
      return next;
    });
  }, []);
  return [display, update];
}
