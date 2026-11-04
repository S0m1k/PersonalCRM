/**
 * API-клиент сохранённых видов списка контактов (/api/views), дублей и мест.
 */

import { apiFetch } from './api';
import type { Contact, ContactSort } from './api';

// ---------------------------------------------------------------------------
// Виды
// ---------------------------------------------------------------------------

export interface ContactView {
  id: string;
  name: string;
  emoji: string;
  /** Параметры списка (ключи как в URL страницы контактов: tag, group, priority, freq, loc, src, inactive) */
  filters: Record<string, string>;
  sort: ContactSort | null;
  /** id колонок таблицы; пусто — по умолчанию */
  columns: string[];
  created_at: string;
}

export interface ViewInput {
  name: string;
  emoji?: string;
  filters?: Record<string, string>;
  sort?: ContactSort | null;
  columns?: string[];
}

export function viewsKey(): string {
  return '/api/views';
}

export function createView(data: ViewInput): Promise<ContactView> {
  return apiFetch<ContactView>('/api/views', { method: 'POST', body: JSON.stringify(data) });
}

export function updateView(id: string, data: Partial<ViewInput>): Promise<ContactView> {
  return apiFetch<ContactView>(`/api/views/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteView(id: string): Promise<void> {
  return apiFetch<void>(`/api/views/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Дубли
// ---------------------------------------------------------------------------

export interface DuplicatePair {
  a: Contact;
  b: Contact;
  score: number;
  reasons: string[];
}

export function duplicatesKey(): string {
  return '/api/contacts/duplicates';
}

export function mergeContacts(keepId: string, mergeIds: string[]): Promise<Contact> {
  return apiFetch<Contact>('/api/contacts/merge', {
    method: 'POST',
    body: JSON.stringify({ keep_id: keepId, merge_ids: mergeIds }),
  });
}

export function dismissDuplicate(aId: string, bId: string): Promise<void> {
  return apiFetch<void>('/api/contacts/duplicates/dismiss', {
    method: 'POST',
    body: JSON.stringify({ a_id: aId, b_id: bId }),
  });
}

// ---------------------------------------------------------------------------
// Места
// ---------------------------------------------------------------------------

export interface Place {
  key: string;
  name: string;
  city: string;
  /** address — название лежит в contact.address; city — только в contact.city */
  kind: 'address' | 'city';
  count: number;
  location: { lat: number; lng: number; label: string } | null;
  contacts: { id: string; name: string }[];
}

export function placesKey(): string {
  return '/api/places';
}

export function createPlace(data: { name: string; city?: string }): Promise<Place> {
  return apiFetch<Place>('/api/places', { method: 'POST', body: JSON.stringify(data) });
}
