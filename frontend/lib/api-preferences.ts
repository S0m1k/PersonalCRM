/** API-клиент настроек пользователя. */

import { apiFetch } from './api';
import type { PriorityLevel } from './priority';

export type PriorityLabels = Record<PriorityLevel, string>;

export function priorityLabelsKey(): string {
  return '/api/preferences/priority-labels';
}

export function savePriorityLabels(labels: PriorityLabels): Promise<PriorityLabels> {
  return apiFetch<PriorityLabels>(priorityLabelsKey(), { method: 'PUT', body: JSON.stringify(labels) });
}
