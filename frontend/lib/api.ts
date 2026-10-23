/**
 * API-клиент для бэкенда PersonalCRM.
 *
 * Обёртка над fetch: автоматически добавляет Bearer-токен из localStorage,
 * выбрасывает ошибку при HTTP-ошибках, типизирует ответы.
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Типы
// ---------------------------------------------------------------------------

export interface Phone {
  value: string;
  label: string;
}

export interface Email {
  value: string;
  label: string;
}

export interface CustomField {
  key: string;
  value: string;
}

export interface Relationship {
  contact_id: string;
  label: string;
}

export interface ExternalIds {
  outlook?: string | null;
  google?: string | null;
  telegram?: string | null;
}

export interface Contact {
  id: string;
  first_name: string;
  last_name: string;
  phones: Phone[];
  emails: Email[];
  company: string;
  position: string;
  city: string;
  birthday: string | null;
  notes: string;
  category: string;
  priority: string;
  custom_fields: CustomField[];
  relationships: Relationship[];
  external_ids: ExternalIds;
  template_id: string | null;
  fields: Record<string, FieldValue>;
  source: string;
  sources: string[];
  last_synced_at: string | null;
  sync_hash: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactCreate {
  first_name?: string;
  last_name?: string;
  phones?: Phone[];
  emails?: Email[];
  company?: string;
  position?: string;
  city?: string;
  birthday?: string | null;
  notes?: string;
  category?: string;
  priority?: string;
  custom_fields?: CustomField[];
  relationships?: Relationship[];
  /** "" в PATCH — снять шаблон */
  template_id?: string | null;
  fields?: Record<string, FieldValue>;
}

export type ContactUpdate = Partial<ContactCreate>;

export type FieldValue = string | number | boolean;
export type FieldType = 'text' | 'longtext' | 'date' | 'number' | 'select' | 'url' | 'bool';

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  options: string[];
}

export interface Template {
  id: string;
  name: string;
  icon: string;
  fields: FieldDef[];
  builtin: boolean;
  created_at: string;
  updated_at: string;
}

export interface TemplateInput {
  name: string;
  icon?: string;
  fields: Array<Omit<FieldDef, 'key'> & { key?: string }>;
}

export type QuestionStatus = 'open' | 'answered' | 'dropped';

export interface Question {
  id: string;
  contact_id: string;
  contact_name: string;
  text: string;
  status: QuestionStatus;
  answer: string;
  answered_at: string | null;
  /** "next_meeting" | YYYY-MM-DD | null */
  ask_at: string | null;
  source: 'manual' | 'ai' | 'meeting';
  created_at: string;
  updated_at: string;
}

export interface QuestionUpdate {
  text?: string;
  status?: QuestionStatus;
  answer?: string;
  ask_at?: string | null;
}

export interface UpcomingBirthday {
  contact_id: string;
  name: string;
  date: string;
  days_until: number;
  turns: number | null;
}

export interface RecentContact {
  id: string;
  name: string;
  company: string;
  position: string;
  template_id: string | null;
}

export interface HomeSummary {
  stats: { contacts: number; open_questions: number };
  birthdays: UpcomingBirthday[];
  recent: RecentContact[];
  open_questions: Question[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ---------------------------------------------------------------------------
// Хелперы
// ---------------------------------------------------------------------------

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('crm_token');
}

export function saveToken(token: string): void {
  localStorage.setItem('crm_token', token);
}

export function clearToken(): void {
  localStorage.removeItem('crm_token');
}

export function isLoggedIn(): boolean {
  return !!getToken();
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Человекочитаемый текст ошибки из ответа FastAPI ({detail: string | string[] | [{msg}]}). */
async function errorMessage(resp: Response): Promise<string> {
  const text = await resp.text().catch(() => resp.statusText);
  try {
    const detail: unknown = JSON.parse(text).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: unknown) => (typeof d === 'string' ? d : (d as { msg?: string }).msg ?? ''))
        .filter(Boolean)
        .join('; ');
    }
  } catch {
    // не JSON — вернём как есть
  }
  return text || resp.statusText;
}

/** Fetcher для SWR: ключ — путь API. */
export function fetcher<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const resp = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });

  if (resp.status === 401) {
    clearToken();
    if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new ApiError(401, 'Не авторизован');
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, await errorMessage(resp));
  }

  // 204 No Content
  if (resp.status === 204) {
    return undefined as T;
  }

  return resp.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function login(username: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_URL}/api/auth/login/json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, 'Неверный логин или пароль');
  }
  return resp.json() as Promise<TokenResponse>;
}

// ---------------------------------------------------------------------------
// Contacts
// ---------------------------------------------------------------------------

export interface ListParams {
  q?: string;
  category?: string;
  priority?: string;
  skip?: number;
  limit?: number;
}

export async function getContacts(params: ListParams = {}): Promise<Contact[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set('q', params.q);
  if (params.category) qs.set('category', params.category);
  if (params.priority) qs.set('priority', params.priority);
  if (params.skip !== undefined) qs.set('skip', String(params.skip));
  if (params.limit !== undefined) qs.set('limit', String(params.limit));

  const query = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<Contact[]>(`/api/contacts/${query}`);
}

export async function getContact(id: string): Promise<Contact> {
  return apiFetch<Contact>(`/api/contacts/${id}`);
}

export async function createContact(data: ContactCreate): Promise<Contact> {
  return apiFetch<Contact>('/api/contacts/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateContact(id: string, data: ContactUpdate): Promise<Contact> {
  return apiFetch<Contact>(`/api/contacts/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteContact(id: string): Promise<void> {
  return apiFetch<void>(`/api/contacts/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Sync (подключения провайдеров + синхронизация)
// ---------------------------------------------------------------------------

export interface SyncConnection {
  id: string;
  provider: string;
  sync_contacts: boolean;
  sync_calendar: boolean;
  contacts_last_sync: string | null;
  token_expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SyncStats {
  created: number;
  updated: number;
  deleted: number;
  merged: number;
  skipped: number;
  errors: number;
}

export interface SyncLogEntry {
  id: string;
  connection_id: string;
  type: string;
  action: string;
  stats: SyncStats;
  errors: { contact_name: string; error: string }[];
  started_at: string;
  completed_at: string | null;
}

export async function getConnections(): Promise<SyncConnection[]> {
  return apiFetch<SyncConnection[]>('/api/sync/connections');
}

/**
 * Начать подключение Outlook. Возвращает authorize_url (редиректим туда),
 * либо бросает ApiError со статусом 501, если Azure не настроен.
 */
export async function connectMicrosoft(): Promise<{ authorize_url: string; state: string }> {
  return apiFetch<{ authorize_url: string; state: string }>('/api/sync/connect/microsoft', {
    method: 'POST',
  });
}

export async function connectGoogle(): Promise<{ authorize_url: string; state: string }> {
  return apiFetch<{ authorize_url: string; state: string }>('/api/sync/connect/google', {
    method: 'POST',
  });
}

export async function pushContact(
  connectionId: string,
  contactId: string,
): Promise<{ status: string; provider: string; external_id: string | null }> {
  return apiFetch(`/api/sync/contacts/${connectionId}/push/${contactId}`, { method: 'POST' });
}

export async function deleteConnection(id: string): Promise<void> {
  return apiFetch<void>(`/api/sync/connections/${id}`, { method: 'DELETE' });
}

export async function triggerSync(connectionId: string): Promise<SyncLogEntry> {
  return apiFetch<SyncLogEntry>(`/api/sync/contacts/${connectionId}`, { method: 'POST' });
}

export async function getSyncLog(): Promise<SyncLogEntry[]> {
  return apiFetch<SyncLogEntry[]>('/api/sync/log');
}

// ---------------------------------------------------------------------------
// Import (файлы CSV / vCard / Telegram)
// ---------------------------------------------------------------------------

export interface ImportUploadResult {
  import_id: string;
  format: string;
  count: number;
}

export interface PreviewMatch {
  existing_id: string;
  name: string;
  score: number;
  reasons: string[];
}

export interface PreviewItem {
  index: number;
  contact: Contact;
  classification: 'new' | 'auto_merge' | 'suggest_merge';
  best_match: PreviewMatch | null;
}

export interface ImportPreview {
  import_id: string;
  total: number;
  new_count: number;
  auto_merge_count: number;
  suggest_count: number;
  items: PreviewItem[];
}

export interface ImportDecision {
  index: number;
  action: 'create' | 'merge' | 'skip';
  existing_id?: string;
}

export interface ImportConfirmResult {
  created: number;
  merged: number;
  skipped: number;
}

/** Загрузка файла — multipart, поэтому Content-Type выставляет браузер сам. */
export async function uploadImportFile(file: File): Promise<ImportUploadResult> {
  const token = getToken();
  const form = new FormData();
  form.append('file', file);

  const resp = await fetch(`${API_URL}/api/import/upload`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (resp.status === 401) {
    clearToken();
    throw new ApiError(401, 'Не авторизован');
  }
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new ApiError(resp.status, text);
  }
  return resp.json() as Promise<ImportUploadResult>;
}

export async function getImportPreview(importId: string): Promise<ImportPreview> {
  return apiFetch<ImportPreview>(`/api/import/${importId}/preview`);
}

export async function confirmImport(
  importId: string,
  decisions: ImportDecision[] = [],
): Promise<ImportConfirmResult> {
  return apiFetch<ImportConfirmResult>(`/api/import/${importId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ decisions }),
  });
}

// ---------------------------------------------------------------------------
// Шаблоны карточек
// ---------------------------------------------------------------------------

export function createTemplate(data: TemplateInput): Promise<Template> {
  return apiFetch<Template>('/api/templates', { method: 'POST', body: JSON.stringify(data) });
}

export function updateTemplate(id: string, data: Partial<TemplateInput>): Promise<Template> {
  return apiFetch<Template>(`/api/templates/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteTemplate(id: string): Promise<void> {
  return apiFetch<void>(`/api/templates/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Вопросы к человеку
// ---------------------------------------------------------------------------

export function createQuestion(contactId: string, text: string, askAt: string | null = null): Promise<Question> {
  return apiFetch<Question>('/api/questions', {
    method: 'POST',
    body: JSON.stringify({ contact_id: contactId, text, ask_at: askAt }),
  });
}

export function updateQuestion(id: string, data: QuestionUpdate): Promise<Question> {
  return apiFetch<Question>(`/api/questions/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteQuestion(id: string): Promise<void> {
  return apiFetch<void>(`/api/questions/${id}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Главная
// ---------------------------------------------------------------------------

/** Ключ SWR главной: с локальной датой (сервер может жить в UTC). */
export function homeKey(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
  return `/api/home?today=${local}`;
}
