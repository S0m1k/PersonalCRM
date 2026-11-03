/**
 * API-клиент данных Sprint 11: группы, теги, взаимодействия (Timeline), Keep in touch, сеть.
 *
 * Типы контакта (Contact, ContactUpdate) — в api.ts. Ключи SWR — функции *Key():
 *   useSWR(keepInTouchKey(), fetcher<KeepInTouchBuckets>)
 */

import { apiFetch } from './api';
import type { Contact } from './api';

// ---------------------------------------------------------------------------
// Группы
// ---------------------------------------------------------------------------

export interface Group {
  id: string;
  name: string;
  emoji: string;
  /** токен акцента или #rrggbb */
  color: string;
  description: string;
  member_count: number;
  created_at: string;
}

export interface GroupInput {
  name: string;
  emoji?: string;
  color?: string;
  description?: string;
}

export function groupsKey(): string {
  return '/api/groups';
}

export function createGroup(data: GroupInput): Promise<Group> {
  return apiFetch<Group>('/api/groups', { method: 'POST', body: JSON.stringify(data) });
}

export function updateGroup(id: string, data: Partial<GroupInput>): Promise<Group> {
  return apiFetch<Group>(`/api/groups/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

/** Удаляет группу и убирает её у всех контактов. */
export function deleteGroup(id: string): Promise<void> {
  return apiFetch<void>(`/api/groups/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Теги
// ---------------------------------------------------------------------------

export interface TagCount {
  tag: string;
  count: number;
}

export function tagsKey(): string {
  return '/api/tags';
}

/** Переименовать тег; если новое имя уже есть — теги сольются. Возвращает число затронутых контактов. */
export function renameTag(from: string, to: string): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>('/api/tags/rename', {
    method: 'POST',
    body: JSON.stringify({ from, to }),
  });
}

/** Убрать тег у всех контактов. */
export function deleteTag(tag: string): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>(`/api/tags/${encodeURIComponent(tag)}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Взаимодействия (Timeline)
// ---------------------------------------------------------------------------

export type InteractionKind = 'note' | 'call' | 'meeting' | 'message' | 'email' | 'other';
export type InteractionSource = 'manual' | 'calendar' | 'ai' | 'import';

export interface Interaction {
  /** у встреч из календаря — "event:<id события>" */
  id: string;
  contact_ids: string[];
  kind: InteractionKind;
  title: string;
  body: string;
  occurred_at: string;
  source: InteractionSource;
  /** true — встреча из календаря, менять только в календаре */
  read_only: boolean;
  created_at: string;
  updated_at: string;
}

export interface InteractionPage {
  items: Interaction[];
  /** передать в params.cursor за следующей страницей; null — конец */
  next_cursor: string | null;
}

export interface InteractionInput {
  contact_ids: string[];
  kind?: InteractionKind;
  title?: string;
  body?: string;
  /** ISO-время; по умолчанию — сейчас */
  occurred_at?: string;
  source?: InteractionSource;
}

export type InteractionUpdate = Partial<Omit<InteractionInput, 'source'>>;

export interface InteractionListParams {
  contact_id?: string;
  kind?: InteractionKind;
  /** ISO-время, не раньше */
  from?: string;
  /** ISO-время, не позже */
  to?: string;
  q?: string;
  cursor?: string;
  /** 1..200, по умолчанию 30 */
  limit?: number;
  /** подмешать прошедшие события календаря как встречи (read_only) */
  include_events?: boolean;
}

/** Ключ SWR ленты (одна страница); для «Показать ещё» передавайте cursor из предыдущей. */
export function interactionsKey(params: InteractionListParams = {}): string {
  const qs = new URLSearchParams();
  if (params.contact_id) qs.set('contact_id', params.contact_id);
  if (params.kind) qs.set('kind', params.kind);
  if (params.from) qs.set('from', params.from);
  if (params.to) qs.set('to', params.to);
  if (params.q) qs.set('q', params.q);
  if (params.cursor) qs.set('cursor', params.cursor);
  if (params.limit !== undefined) qs.set('limit', String(params.limit));
  if (params.include_events) qs.set('include_events', 'true');
  const query = qs.toString();
  return `/api/interactions${query ? `?${query}` : ''}`;
}

export function getInteractions(params: InteractionListParams = {}): Promise<InteractionPage> {
  return apiFetch<InteractionPage>(interactionsKey(params));
}

export function createInteraction(data: InteractionInput): Promise<Interaction> {
  return apiFetch<Interaction>('/api/interactions', { method: 'POST', body: JSON.stringify(data) });
}

export function updateInteraction(id: string, data: InteractionUpdate): Promise<Interaction> {
  return apiFetch<Interaction>(`/api/interactions/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteInteraction(id: string): Promise<void> {
  return apiFetch<void>(`/api/interactions/${id}`, { method: 'DELETE' });
}

/** Взаимодействие в сводке главной: + имена людей. */
export interface HomeInteraction extends Interaction {
  contacts: Array<{ id: string; name: string }>;
}

// ---------------------------------------------------------------------------
// Keep in touch
// ---------------------------------------------------------------------------

export interface KeepInTouchItem {
  contact_id: string;
  name: string;
  company: string;
  tags: string[];
  importance: number | null;
  frequency_days: number;
  /** YYYY-MM-DD: последнее общение (или дата создания) + частота */
  due_date: string;
  /** 0, если срок не прошёл */
  days_overdue: number;
  /** 0, если срок прошёл */
  days_until: number;
  last_interaction_at: string | null;
  snoozed_until: string | null;
}

export interface KeepInTouchBuckets {
  overdue: KeepInTouchItem[];
  /** срок сегодня или в ближайшие 7 дней */
  due_soon: KeepInTouchItem[];
  upcoming: KeepInTouchItem[];
  snoozed: KeepInTouchItem[];
}

function localToday(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
}

/** Ключ SWR Keep in touch — с локальной датой пользователя (сервер может жить в UTC). */
export function keepInTouchKey(): string {
  return `/api/keep-in-touch?today=${localToday()}`;
}

/** Отложить напоминание на N дней (1..365). Возвращает обновлённый контакт. */
export function snoozeContact(contactId: string, days: number): Promise<Contact> {
  return apiFetch<Contact>(`/api/contacts/${contactId}/snooze`, {
    method: 'POST',
    body: JSON.stringify({ days, today: localToday() }),
  });
}

/** «Связались»: создаёт быстрое взаимодействие и снимает отложенное напоминание. */
export function markTouched(
  contactId: string,
  options: { kind?: InteractionKind; title?: string; body?: string } = {},
): Promise<Interaction> {
  return apiFetch<Interaction>(`/api/contacts/${contactId}/touched`, {
    method: 'POST',
    body: JSON.stringify(options),
  });
}

// ---------------------------------------------------------------------------
// Сеть (граф)
// ---------------------------------------------------------------------------

export interface NetworkNode {
  id: string;
  name: string;
  company: string;
  group_ids: string[];
  tags: string[];
  importance: number | null;
}

export interface NetworkEdge {
  source: string;
  target: string;
  /** relationship — связь из карточки; together — вместе во взаимодействиях / встречах */
  kind: 'relationship' | 'together';
  label: string;
  weight: number;
}

export interface NetworkGraph {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  /** контактов больше 500 — показаны самые важные */
  truncated: boolean;
}

/** Ключ SWR графа; min_weight — минимум совместных взаимодействий для ребра together. */
export function networkKey(minWeight = 1): string {
  return `/api/network?min_weight=${minWeight}`;
}
