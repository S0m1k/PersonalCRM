/**
 * Состояние списка контактов (фильтры, сортировка, колонки) ⇄ URL ⇄ сохранённый вид ⇄ запрос к API.
 * Ключи совпадают в URL и в ContactView.filters, поэтому ссылка на вид и «поделиться» работают одинаково.
 */

import type { ContactSort } from './api';

export const FILTER_KEYS = ['tag', 'group', 'priority', 'freq', 'loc', 'src', 'inactive'] as const;
export type FilterKey = (typeof FILTER_KEYS)[number];

export interface ListState {
  q: string;
  filters: Partial<Record<FilterKey, string>>;
  sort: ContactSort | null;
  /** null — колонки по умолчанию */
  columns: string[] | null;
}

export interface ViewBase {
  filters: Record<string, string>;
  sort: ContactSort | null;
  columns: string[];
}

export const SORTS: { id: ContactSort; label: string }[] = [
  { id: 'name', label: 'По имени' },
  { id: 'last_interaction', label: 'По последнему общению' },
  { id: 'created', label: 'По дате добавления' },
  { id: 'importance', label: 'По важности' },
];

export const COLUMNS = [
  { id: 'position', label: 'Должность' },
  { id: 'company', label: 'Компания' },
  { id: 'frequency', label: 'Частота' },
  { id: 'priority', label: 'Приоритет' },
  { id: 'tags', label: 'Теги' },
  { id: 'groups', label: 'Группы' },
  { id: 'social', label: 'Соцсети' },
  { id: 'last', label: 'Последнее взаимодействие' },
  { id: 'created', label: 'Добавлен' },
] as const;
export type ColumnId = (typeof COLUMNS)[number]['id'];

export const DEFAULT_COLUMNS: ColumnId[] = ['position', 'company', 'frequency', 'priority', 'tags', 'social', 'last'];

const COLUMN_IDS: string[] = COLUMNS.map((c) => c.id);

function isSort(value: string | null | undefined): value is ContactSort {
  return SORTS.some((s) => s.id === value);
}

/** URL-параметры → состояние. `view` — подложка из сохранённого вида (URL важнее). */
export function parseState(params: URLSearchParams, view?: ViewBase | null): ListState {
  const filters: Partial<Record<FilterKey, string>> = {};
  for (const key of FILTER_KEYS) {
    const value = params.get(key) ?? view?.filters[key];
    if (value) filters[key] = value;
  }
  const sortParam = params.get('sort');
  const colsParam = params.get('cols');
  const viewCols = view && view.columns.length ? view.columns : null;
  const cols = (colsParam ? colsParam.split(',') : viewCols)?.filter((c) => COLUMN_IDS.includes(c)) ?? [];
  return {
    q: params.get('q') ?? '',
    filters,
    sort: isSort(sortParam) ? sortParam : (view?.sort ?? null),
    columns: cols.length ? cols : null,
  };
}

/** Состояние → URL-параметры. */
export function stateToParams(state: ListState, viewId: string | null): URLSearchParams {
  const params = new URLSearchParams();
  if (viewId) params.set('view', viewId);
  if (state.q) params.set('q', state.q);
  for (const key of FILTER_KEYS) {
    const value = state.filters[key];
    if (value) params.set(key, value);
  }
  if (state.sort) params.set('sort', state.sort);
  if (state.columns) params.set('cols', state.columns.join(','));
  return params;
}

/** Параметры запроса /api/contacts/ (и /count) без skip/limit. */
export function stateToQuery(state: ListState): URLSearchParams {
  const qs = new URLSearchParams();
  const f = state.filters;
  if (state.q) qs.set('q', state.q);
  if (f.tag) qs.set('tag', f.tag);
  if (f.group) qs.set('group_id', f.group);
  if (f.priority === 'unset') qs.set('has_priority', 'false');
  else if (f.priority) qs.set('priority', f.priority);
  if (f.freq === 'set') qs.set('has_frequency', 'true');
  if (f.freq === 'unset') qs.set('has_frequency', 'false');
  if (f.loc === '1') qs.set('has_location', 'true');
  if (f.loc === '0') qs.set('has_location', 'false');
  if (f.src) qs.set('source', f.src);
  if (f.inactive && Number(f.inactive) > 0) qs.set('inactive_days', f.inactive);
  if (state.sort) qs.set('sort', state.sort);
  return qs;
}

export function activeFilterCount(state: ListState): number {
  return FILTER_KEYS.filter((k) => state.filters[k]).length;
}

/** Ссылка на соцсеть по значению из карточки: полный URL или ник. */
export function socialHref(kind: string, value: string): string | undefined {
  if (!value) return undefined;
  if (/^https?:\/\//i.test(value)) return value;
  const handle = value.replace(/^@/, '');
  const bases: Record<string, string> = {
    telegram: 'https://t.me/',
    instagram: 'https://instagram.com/',
    twitter: 'https://x.com/',
    linkedin: 'https://www.linkedin.com/in/',
    facebook: 'https://facebook.com/',
  };
  return bases[kind] ? `${bases[kind]}${encodeURIComponent(handle)}` : undefined;
}
