import type { Contact } from './api';
import { plural } from './utils';

/** Годы 1604 и ≤1900 в данных означают «год неизвестен» (так же, как в formatDate). */
const UNKNOWN_YEAR_MAX = 1900;
const MONTHS_AHEAD = 12;

const MONTH_FMT = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' });
const DAY_FMT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', weekday: 'short' });

export interface BirthdayEntry {
  contact: Contact;
  /** ближайшая дата, YYYY-MM-DD */
  date: string;
  daysUntil: number;
  /** сколько исполнится; null — год рождения неизвестен */
  turns: number | null;
  monthLabel: string;
  dateLabel: string;
  untilLabel: string;
}

function utcNoon(y: number, m: number, d: number): number {
  return Date.UTC(y, m, d, 12);
}

/** Ближайшая дата дня рождения не раньше today; 29 февраля в невисокосный год → 28 февраля. */
function nextOccurrence(month: number, day: number, today: Date): Date {
  const y = today.getFullYear();
  const todayMs = utcNoon(y, today.getMonth(), today.getDate());
  for (const year of [y, y + 1]) {
    const isLeap = new Date(year, 1, 29).getDate() === 29;
    const d = month === 1 && day === 29 && !isLeap ? 28 : day;
    const ms = utcNoon(year, month, d);
    if (ms >= todayMs) return new Date(ms);
  }
  return new Date(utcNoon(y + 1, month, day));
}

export function untilLabel(days: number): string {
  if (days === 0) return 'Сегодня';
  if (days === 1) return 'Завтра';
  return `через ${days} ${plural(days, 'день', 'дня', 'дней')}`;
}

/** Дни рождения ближайших 12 месяцев, по возрастанию даты. */
export function upcomingBirthdays(contacts: Contact[], today: Date): BirthdayEntry[] {
  const todayMs = utcNoon(today.getFullYear(), today.getMonth(), today.getDate());
  const horizon = utcNoon(today.getFullYear(), today.getMonth() + MONTHS_AHEAD, today.getDate());
  const result: BirthdayEntry[] = [];

  for (const contact of contacts) {
    if (!contact.birthday) continue;
    const [y, m, d] = contact.birthday.split('-').map(Number);
    if (!m || !d) continue;
    const next = nextOccurrence(m - 1, d, today);
    if (next.getTime() >= horizon) continue;
    const daysUntil = Math.round((next.getTime() - todayMs) / 86_400_000);
    result.push({
      contact,
      date: next.toISOString().slice(0, 10),
      daysUntil,
      turns: y > UNKNOWN_YEAR_MAX ? next.getUTCFullYear() - y : null,
      monthLabel: capitalize(MONTH_FMT.format(next)),
      dateLabel: DAY_FMT.format(next),
      untilLabel: untilLabel(daysUntil),
    });
  }
  return result.sort((a, b) => a.daysUntil - b.daysUntil);
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
