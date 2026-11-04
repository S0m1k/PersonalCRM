/** API-клиент экрана «Сеть»: вселенная и инсайты. Граф связей — в api-crm.ts (networkKey). */

export interface UniverseCluster {
  id: number;
  label: string;
  contact_ids: string[];
}

export interface Universe {
  /** false — мало данных профиля, кластеров нет */
  ready: boolean;
  required: number;
  profiled: number;
  clusters: UniverseCluster[];
  positions: Record<string, { x: number; y: number }>;
}

export function universeKey(): string {
  return '/api/network/universe';
}

export interface Slice {
  label: string;
  count: number;
}

export interface MonthPoint {
  month: string;
  added: number;
  total: number;
}

export interface Insights {
  total: number;
  enough: boolean;
  required: number;
  by_company: Slice[];
  by_city: Slice[];
  by_tag: Slice[];
  by_group: Slice[];
  by_frequency: Slice[];
  by_recency: Slice[];
  growth: MonthPoint[];
}

export function insightsKey(): string {
  return '/api/network/insights';
}
