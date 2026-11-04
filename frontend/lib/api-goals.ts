/**
 * API-клиент «Целей и стратегий»: /api/goals.
 * Ключи SWR — функции *Key(): useSWR(goalsKey()), useSWR(goalsMetricsKey(30)).
 */

import { apiFetch } from './api';

export type ApproachId = 'max_contacts' | 'deep_relations' | 'life_balance' | 'custom';
export type GoalPeriod = 30 | 90 | 180;

export interface MaxContactsSettings {
  new_per_month: number;
  frequency_days: number;
  coverage_target_pct: number;
  coverage_window_days: number;
}
export interface CircleSetting {
  capacity: number;
  frequency_days: number;
}
export interface DeepRelationsSettings {
  circles: CircleSetting[];
}
export interface Sphere {
  name: string;
  target_per_month: number;
}
export interface LifeBalanceSettings {
  spheres: Sphere[];
}
export type RuleKind = 'tag' | 'group' | 'priority' | 'life_area' | 'circle';
export interface Rule {
  kind: RuleKind;
  value: string;
  frequency_days: number;
}
export interface CustomSettings {
  rules: Rule[];
  new_per_month: number | null;
  touches_per_month: number | null;
}

export interface GoalSettings {
  max_contacts: MaxContactsSettings;
  deep_relations: DeepRelationsSettings;
  life_balance: LifeBalanceSettings;
  custom: CustomSettings;
}

export interface ApproachInfo {
  id: ApproachId;
  name: string;
  icon: string;
  tagline: string;
  philosophy: string;
  principles: string[];
  does: string[];
  metrics: string[];
}

export interface GoalsState {
  primary: ApproachId | null;
  enabled: ApproachId[];
  settings: GoalSettings;
  assignments: Record<string, { circle: number }>;
  updated_at: string | null;
  catalogue: ApproachInfo[];
}

export interface GoalsUpdate {
  primary?: ApproachId;
  clear_primary?: boolean;
  enabled?: ApproachId[];
  settings?: Partial<{ [K in ApproachId]: GoalSettings[K] }>;
}

export interface TargetMetric {
  key: string;
  label: string;
  value: number;
  target: number;
  unit: string;
  /** 0..1 */
  progress: number;
}

export interface MonthPoint {
  x: string;
  label: string;
  y: number;
}

export interface CircleMetric {
  circle: number;
  name: string;
  capacity: number;
  frequency_days: number;
  count: number;
  overflow: number;
  on_schedule: number;
  overdue: number;
  free: number;
  on_schedule_pct: number | null;
  avg_days_since: number | null;
}

export interface SphereMetric {
  name: string;
  target_per_month: number;
  touches: number;
  per_month: number;
  contacts: number;
  pct_of_target: number | null;
  share_actual: number;
  share_target: number;
}

export interface RadarPoint {
  sphere: string;
  actual: number;
  target: number;
}

export interface RuleMetric {
  label: string;
  frequency_days: number;
  count: number;
  on_schedule: number;
  on_schedule_pct: number | null;
}

export interface ApproachMetrics {
  id: ApproachId;
  name: string;
  period_days: number;
  targets: TargetMetric[];
  hints: string[];
  new_per_month?: MonthPoint[];
  coverage?: { touched: number; total: number; pct: number; window_days: number };
  diversity?: { companies: number; cities: number };
  circles?: CircleMetric[];
  unassigned?: number;
  spheres?: SphereMetric[];
  radar?: RadarPoint[];
  radar_by_period?: Record<string, RadarPoint[]>;
  rules?: RuleMetric[];
}

export interface GoalsMetrics {
  period: GoalPeriod;
  primary: ApproachId | null;
  approaches: ApproachMetrics[];
}

export interface NextStep {
  contact_id: string;
  name: string;
  frequency_days: number;
  days_since: number | null;
  days_overdue: number;
  approach: ApproachId;
  reason: string;
}

export interface NextSteps {
  primary: ApproachId | null;
  items: NextStep[];
}

export interface ApplyItem {
  contact_id: string;
  name: string;
  current: number | null;
  recommended: number;
  reason: string;
  action: 'change' | 'same' | 'skipped_manual';
  was_manual: boolean;
}

export interface ApplyPreview {
  will_change: number;
  unchanged: number;
  skipped_manual: number;
  by_frequency: { frequency_days: number; count: number }[];
  items: ApplyItem[];
  overwrite: boolean;
}

export interface ApplyResult {
  changed: number;
  skipped_manual: number;
  unchanged: number;
}

export const goalsKey = (): string => '/api/goals';
export const goalsMetricsKey = (period: GoalPeriod): string => `/api/goals/metrics?period=${period}`;
export const goalsStepsKey = (): string => '/api/goals/recommendations';

const json = (body: unknown) => JSON.stringify(body);

export function updateGoals(data: GoalsUpdate): Promise<GoalsState> {
  return apiFetch<GoalsState>('/api/goals', { method: 'PUT', body: json(data) });
}

export function previewApply(overwrite: boolean): Promise<ApplyPreview> {
  return apiFetch<ApplyPreview>('/api/goals/apply/preview', { method: 'POST', body: json({ overwrite }) });
}

export function applyStrategy(overwrite: boolean): Promise<ApplyResult> {
  return apiFetch<ApplyResult>('/api/goals/apply', { method: 'POST', body: json({ overwrite }) });
}

/** circle: 1..4 или null — снять назначение. */
export function assignCircles(assignments: Record<string, number | null>): Promise<GoalsState> {
  return apiFetch<GoalsState>('/api/goals/assignments', { method: 'PUT', body: json({ assignments }) });
}
