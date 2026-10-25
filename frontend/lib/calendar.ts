/**
 * Даты для календаря: недели с понедельника, форматирование времени событий,
 * значения для <input type="date|datetime-local"> в локальном времени браузера.
 */

import type { CalendarEvent } from './api';

const DAY_MS = 86_400_000;

export const TIME_FMT = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' });
export const DAY_FMT = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
export const SHORT_DAY_FMT = new Intl.DateTimeFormat('ru-RU', { weekday: 'short', day: 'numeric' });
const DAY_MONTH_FMT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });

export function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

export function addDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days, date.getHours(), date.getMinutes());
}

/** Понедельник недели, в которую попадает дата. */
export function startOfWeek(date: Date): Date {
  const day = startOfDay(date);
  return addDays(day, -((day.getDay() + 6) % 7));
}

export function sameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** «2 – 8 ноября 2026» */
export function weekLabel(weekStart: Date): string {
  const end = addDays(weekStart, 6);
  const first = weekStart.getMonth() === end.getMonth() ? `${weekStart.getDate()}` : DAY_MONTH_FMT.format(weekStart);
  return `${first} – ${DAY_MONTH_FMT.format(end)} ${end.getFullYear()}`;
}

/**
 * Границы события в локальном времени. «Весь день» хранится как полночь UTC —
 * берём из неё дату, иначе в часовых поясах западнее UTC событие съехало бы на день раньше.
 */
export function eventBounds(event: Pick<CalendarEvent, 'start' | 'end' | 'all_day'>): { start: Date; end: Date } {
  if (event.all_day) {
    const [sy, sm, sd] = event.start.slice(0, 10).split('-').map(Number);
    const [ey, em, ed] = event.end.slice(0, 10).split('-').map(Number);
    return { start: new Date(sy, sm - 1, sd), end: new Date(ey, em - 1, ed) };
  }
  return { start: new Date(event.start), end: new Date(event.end) };
}

/** Событие пересекается с днём (локальным). */
export function occursOn(event: CalendarEvent, day: Date): boolean {
  const { start, end } = eventBounds(event);
  const dayStart = startOfDay(day).getTime();
  const dayEnd = dayStart + DAY_MS;
  const s = start.getTime();
  // Событие нулевой длины (напоминание) — в день своего начала
  return s < dayEnd && (end.getTime() > dayStart || (s === end.getTime() && s >= dayStart));
}

/** «10:00 – 11:30», «весь день», «с 10:00» для многодневных. */
export function timeRange(event: CalendarEvent, day?: Date): string {
  if (event.all_day) return 'весь день';
  const { start, end } = eventBounds(event);
  if (day && !sameDay(start, day)) return sameDay(end, day) ? `до ${TIME_FMT.format(end)}` : 'весь день';
  if (!sameDay(start, end)) return `с ${TIME_FMT.format(start)}`;
  return start.getTime() === end.getTime() ? TIME_FMT.format(start) : `${TIME_FMT.format(start)} – ${TIME_FMT.format(end)}`;
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

/** Значение для <input type="date"> */
export function toDateInput(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Значение для <input type="datetime-local"> */
export function toDateTimeInput(date: Date): string {
  return `${toDateInput(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** Часовой пояс браузера (IANA) — в нём бэкенд читает время из формы. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

/** Следующий ровный час — время по умолчанию для новой встречи. */
export function nextHour(day: Date = new Date()): Date {
  const now = new Date();
  const base = sameDay(day, now) ? now : new Date(day.getFullYear(), day.getMonth(), day.getDate(), 9);
  return new Date(base.getFullYear(), base.getMonth(), base.getDate(), base.getHours() + (sameDay(day, now) ? 1 : 0));
}
