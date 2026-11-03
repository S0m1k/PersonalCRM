import type { TagColor } from '@/lib/utils';

/** Уровни приоритета (как в Priority Map Dex). Пустая строка — «не задан». */
export const PRIORITY_LEVELS = ['top', 'high', 'medium', 'low', 'none'] as const;
export type PriorityLevel = (typeof PRIORITY_LEVELS)[number];

export const PRIORITY_META: Record<PriorityLevel, { label: string; color: TagColor; hotkey: string }> = {
  top: { label: 'Топ', color: 'purple', hotkey: '1' },
  high: { label: 'Высокий', color: 'red', hotkey: '2' },
  medium: { label: 'Средний', color: 'yellow', hotkey: '3' },
  low: { label: 'Низкий', color: 'gray', hotkey: '4' },
  none: { label: 'Нет', color: 'gray', hotkey: '5' },
};

export function isPriorityLevel(value: string): value is PriorityLevel {
  return (PRIORITY_LEVELS as readonly string[]).includes(value);
}

/** Подпись уровня; названия уровней можно переопределить (настройки Priority Map). */
export function priorityLabel(value: string, overrides?: Partial<Record<PriorityLevel, string>>): string {
  if (!isPriorityLevel(value)) return value ? value : 'Не задан';
  return overrides?.[value] || PRIORITY_META[value].label;
}
