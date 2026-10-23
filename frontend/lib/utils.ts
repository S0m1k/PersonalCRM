import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export type TagColor = 'gray' | 'brown' | 'orange' | 'yellow' | 'green' | 'blue' | 'purple' | 'pink' | 'red';

const AVATAR_COLORS: TagColor[] = ['orange', 'yellow', 'green', 'blue', 'purple', 'pink', 'red', 'brown'];

/** Стабильный цвет по строке: один и тот же человек — всегда один цвет. */
export function colorFor(seed: string): TagColor {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase();
}

export function fullName(person: { first_name?: string; last_name?: string }): string {
  return [person.first_name, person.last_name].filter(Boolean).join(' ').trim();
}

/** 1 вопрос, 2 вопроса, 5 вопросов */
export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

const DATE_FMT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long' });
const DATE_YEAR_FMT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });

/** "2026-10-21" → "21 октября 2026"; год скрывается для дат без года (1604/1900). */
export function formatDate(iso: string | null | undefined, withYear = true): string {
  if (!iso) return '';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return iso;
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return withYear && y > 1900 ? DATE_YEAR_FMT.format(date) : DATE_FMT.format(date);
}

/** «сегодня», «вчера», «3 дня назад», «12 марта» */
export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const days = Math.floor((Date.now() - then) / 86_400_000);
  if (days <= 0) return 'сегодня';
  if (days === 1) return 'вчера';
  if (days < 7) return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`;
  return formatDate(iso.slice(0, 10), new Date(iso).getFullYear() !== new Date().getFullYear());
}

/** Ссылка только http(s) — защита от javascript:/data: в пользовательских данных. */
export function safeUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Что-то пошло не так';
}
