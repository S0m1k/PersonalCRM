/** Модель экрана Keep in Touch: плоские строки из корзин API, колонки доски, подписи срока. */

import { updateContact } from './api';
import type { Contact } from './api';
import { FREQUENCY_PRESETS } from './frequency';
import type { KeepInTouchBuckets } from './api-crm';
import { plural } from './utils';

export type KitStatus = 'overdue' | 'soon' | 'upcoming' | 'snoozed' | 'unset';

export interface KitRow {
  id: string;
  name: string;
  company: string;
  tags: string[];
  frequency_days: number | null;
  /** YYYY-MM-DD; null — частота не задана (или срок пока неизвестен) */
  due_date: string | null;
  days_overdue: number;
  days_until: number;
  last_interaction_at: string | null;
  snoozed_until: string | null;
  status: KitStatus;
}

export const UNSET_COLUMN = 'unset';
export const CUSTOM_COLUMN = 'custom';

export function columnId(days: number | null): string {
  if (!days) return UNSET_COLUMN;
  return FREQUENCY_PRESETS.some((p) => p.days === days) ? String(days) : CUSTOM_COLUMN;
}

/** Плоский список строк из корзин; unset добавляется, если API его вернул. */
export function rowsFromBuckets(buckets: KeepInTouchBuckets): KitRow[] {
  const withFreq = (status: KitStatus, items: KeepInTouchBuckets['overdue']): KitRow[] =>
    items.map((i) => ({
      id: i.contact_id,
      name: i.name,
      company: i.company,
      tags: i.tags,
      frequency_days: i.frequency_days,
      due_date: i.due_date,
      days_overdue: i.days_overdue,
      days_until: i.days_until,
      last_interaction_at: i.last_interaction_at,
      snoozed_until: i.snoozed_until,
      status,
    }));
  const unset: KitRow[] = (buckets.unset ?? []).map((i) => ({
    id: i.contact_id,
    name: i.name,
    company: i.company,
    tags: i.tags,
    frequency_days: null,
    due_date: null,
    days_overdue: 0,
    days_until: 0,
    last_interaction_at: i.last_interaction_at,
    snoozed_until: null,
    status: 'unset',
  }));
  return [
    ...withFreq('overdue', buckets.overdue),
    ...withFreq('soon', buckets.due_soon),
    ...withFreq('upcoming', buckets.upcoming),
    ...withFreq('snoozed', buckets.snoozed),
    ...unset,
  ];
}

/** Строка после смены частоты: срок пересчитывается от последнего общения (если известно). */
export function withFrequency(row: KitRow, days: number | null, today: Date = new Date()): KitRow {
  if (!days) return { ...row, frequency_days: null, due_date: null, days_overdue: 0, days_until: 0, status: 'unset', snoozed_until: null };
  const anchorMs = row.due_date && row.frequency_days
    ? Date.parse(row.due_date) - row.frequency_days * 86_400_000
    : row.last_interaction_at
      ? Date.parse(row.last_interaction_at)
      : null;
  if (anchorMs === null) return { ...row, frequency_days: days, due_date: null, days_overdue: 0, days_until: 0, status: 'upcoming' };
  const due = new Date(anchorMs + days * 86_400_000);
  const delta = Math.floor((startOfDay(today) - startOfDay(due)) / 86_400_000);
  const status: KitStatus = row.snoozed_until ? 'snoozed' : delta > 0 ? 'overdue' : -delta <= 7 ? 'soon' : 'upcoming';
  return {
    ...row,
    frequency_days: days,
    due_date: due.toISOString().slice(0, 10),
    days_overdue: Math.max(delta, 0),
    days_until: Math.max(-delta, 0),
    status,
  };
}

function startOfDay(d: Date): number {
  return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
}

export interface DueBadge {
  text: string;
  tone: 'danger' | 'warning' | 'neutral';
}

const DAYS = (n: number) => `${n} ${plural(n, 'день', 'дня', 'дней')}`;

/** Подпись срока: «просрочено 12 дн.», «сегодня», «через 3 дня», «отложено до 20.11». */
export function dueBadge(row: KitRow): DueBadge | null {
  if (row.status === 'unset' || !row.due_date) return null;
  if (row.status === 'snoozed' && row.snoozed_until) {
    const [, m, d] = row.snoozed_until.split('-');
    return { text: `отложено до ${d}.${m}`, tone: 'neutral' };
  }
  if (row.days_overdue > 0) {
    return { text: `просрочено ${row.days_overdue} дн.`, tone: row.days_overdue > 14 ? 'danger' : 'warning' };
  }
  if (row.days_until === 0) return { text: 'сегодня', tone: 'warning' };
  return { text: `через ${DAYS(row.days_until)}`, tone: 'neutral' };
}

/** PATCH частоты. Отложенное напоминание сохраняем; null снимает частоту вместе с отсрочкой. */
export function setFrequency(row: Pick<KitRow, 'id' | 'snoozed_until'>, days: number | null): Promise<Contact> {
  return updateContact(row.id, { keep_in_touch: { frequency_days: days, snoozed_until: days ? row.snoozed_until : null } });
}

export const SNOOZE_OPTIONS = [1, 3, 7, 14, 30] as const;
