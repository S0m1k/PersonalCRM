/**
 * API напоминаний (/api/reminders) и общие хелперы дат для экранов «Главная» и «Напоминания».
 */

import { apiFetch } from './api';

export type ReminderRepeat = 'none' | 'weekly' | 'monthly' | 'yearly';

export const REPEAT_LABELS: Record<ReminderRepeat, string> = {
  none: 'Не повторять',
  weekly: 'Каждую неделю',
  monthly: 'Каждый месяц',
  yearly: 'Каждый год',
};

export interface Reminder {
  id: string;
  contact_id: string | null;
  /** Пустая строка, если контакта нет или он удалён */
  contact_name: string;
  title: string;
  note: string;
  /** YYYY-MM-DD */
  due_date: string;
  /** HH:MM */
  due_time: string | null;
  repeat: ReminderRepeat;
  done_at: string | null;
  created_at: string;
}

export interface ReminderInput {
  contact_id: string | null;
  title: string;
  note: string;
  due_date: string;
  due_time: string | null;
  repeat: ReminderRepeat;
}

export type ReminderStatus = 'open' | 'done' | 'all';

export interface ReminderListParams {
  status?: ReminderStatus;
  from?: string;
  to?: string;
  contactId?: string;
}

export function remindersKey(params: ReminderListParams = {}): string {
  const qs = new URLSearchParams();
  if (params.status) qs.set('status', params.status);
  if (params.from) qs.set('from', params.from);
  if (params.to) qs.set('to', params.to);
  if (params.contactId) qs.set('contact_id', params.contactId);
  const query = qs.toString();
  return `/api/reminders${query ? `?${query}` : ''}`;
}

export function createReminder(data: ReminderInput): Promise<Reminder> {
  return apiFetch<Reminder>('/api/reminders', { method: 'POST', body: JSON.stringify(data) });
}

export function updateReminder(id: string, data: Partial<ReminderInput>): Promise<Reminder> {
  return apiFetch<Reminder>(`/api/reminders/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

/** Выполнено; у повторяющегося сервер сам создаёт следующее. */
export function completeReminder(id: string): Promise<Reminder> {
  return apiFetch<Reminder>(`/api/reminders/${id}/done`, { method: 'POST' });
}

export function deleteReminder(id: string): Promise<void> {
  return apiFetch<void>(`/api/reminders/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Даты
// ---------------------------------------------------------------------------

const DAY_MS = 86_400_000;
const WEEK_DAYS = 7;

/** Локальная дата YYYY-MM-DD (сервер может жить в UTC). */
export function localISODate(date: Date = new Date()): string {
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/** Целых дней от сегодняшнего дня до due (отрицательное — просрочено). */
export function daysFromToday(due: string, today: string = localISODate()): number {
  return Math.round((Date.parse(`${due}T00:00:00Z`) - Date.parse(`${today}T00:00:00Z`)) / DAY_MS);
}

export type ReminderGroupId = 'overdue' | 'today' | 'week' | 'later';

export function reminderGroup(due: string, today?: string): ReminderGroupId {
  const days = daysFromToday(due, today);
  if (days < 0) return 'overdue';
  if (days === 0) return 'today';
  if (days <= WEEK_DAYS) return 'week';
  return 'later';
}

/** Подпись срока: «Сегодня», «Завтра», «Вчера» или «12 нояб.»; со временем — «Сегодня, 09:30». */
export function dueLabel(r: Pick<Reminder, 'due_date' | 'due_time'>, today?: string): string {
  const days = daysFromToday(r.due_date, today);
  const base =
    days === 0
      ? 'Сегодня'
      : days === 1
        ? 'Завтра'
        : days === -1
          ? 'Вчера'
          : new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' }).format(new Date(`${r.due_date}T00:00:00`));
  return r.due_time ? `${base}, ${r.due_time}` : base;
}
