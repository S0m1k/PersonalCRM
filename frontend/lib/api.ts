/**
 * API-клиент для бэкенда PersonalCRM.
 *
 * Обёртка над fetch: автоматически добавляет Bearer-токен из localStorage,
 * выбрасывает ошибку при HTTP-ошибках, типизирует ответы.
 */

import type { HomeInteraction, KeepInTouchItem } from './api-crm';

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Типы
// ---------------------------------------------------------------------------

export interface Phone {
  value: string;
  label: string;
  /** Ключ номера (+79215535333) — вычисляет сервер, присылать не нужно */
  normalized?: string;
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

/** Как часто хочется общаться с человеком (Keep in touch). */
export interface KeepInTouchSettings {
  /** 1..730 или null — не следить */
  frequency_days: number | null;
  /** YYYY-MM-DD: напоминание отложено до этой даты включительно */
  snoozed_until: string | null;
}

export interface ContactLocation {
  lat: number;
  lng: number;
  label: string;
}

/** http(s)-ссылка или ник (@name); пустая строка — не задано. */
export interface SocialLinks {
  linkedin: string;
  facebook: string;
  instagram: string;
  telegram: string;
  twitter: string;
  website: string;
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
  /** Короткое био (отдельно от notes) */
  description: string;
  tags: string[];
  group_ids: string[];
  keep_in_touch: KeepInTouchSettings;
  /** YYYY-MM-DD */
  first_met_at: string | null;
  first_met_note: string;
  address: string;
  location: ContactLocation | null;
  social: SocialLinks;
  /** Ось Priority Map, 1..5 */
  importance: number | null;
  /** Ось Priority Map, 1..5 */
  closeness: number | null;
  /** Сферы жизни («Колесо баланса») */
  life_areas: string[];
  /** Ставит сервер (взаимодействия + прошедшие встречи); клиент не пишет */
  last_interaction_at: string | null;
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
  description?: string;
  tags?: string[];
  group_ids?: string[];
  keep_in_touch?: KeepInTouchSettings;
  /** В PATCH null очищает поле (так же location, importance, closeness) */
  first_met_at?: string | null;
  first_met_note?: string;
  address?: string;
  location?: ContactLocation | null;
  social?: Partial<SocialLinks>;
  importance?: number | null;
  closeness?: number | null;
  life_areas?: string[];
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
  /** Sprint 11: топ-5 просроченных из Keep in touch */
  keep_in_touch_overdue: KeepInTouchItem[];
  /** Sprint 11: последние 5 взаимодействий с именами людей */
  recent_interactions: HomeInteraction[];
  counts: { groups: number; tags: number };
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

/** Страницы без входа: с них не уводим на /login при 401. */
const AUTH_PAGES = ['/login', '/register'];

const TOO_MANY_REQUESTS = 429;

/** Fetcher для SWR: ключ — путь API. */
export function fetcher<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}

/** Общая обёртка над fetch (Bearer-токен, ошибки → ApiError); используется и в api-*.ts. */
export async function apiFetch<T>(
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
    const path = typeof window !== 'undefined' ? window.location.pathname : '/login';
    if (!AUTH_PAGES.some((page) => path.startsWith(page))) {
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

export interface Me {
  id: string;
  email: string;
  name: string;
  username: string;
  has_carddav_password: boolean;
}

export interface CarddavPassword {
  username: string;
  password: string;
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_URL}/api/auth/login/json`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: email, password }),
  });
  if (resp.status === TOO_MANY_REQUESTS) {
    throw new ApiError(resp.status, 'Слишком много попыток входа. Подождите минуту.');
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, 'Неверный email или пароль');
  }
  return resp.json() as Promise<TokenResponse>;
}

export async function register(email: string, password: string, name: string): Promise<TokenResponse> {
  const resp = await fetch(`${API_URL}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, name }),
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await errorMessage(resp));
  }
  return resp.json() as Promise<TokenResponse>;
}

export const meKey = '/api/auth/me';

/** Сменить пароль. Остальные сессии завершаются — сохраняем новый токен этой вкладки. */
export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const resp = await apiFetch<TokenResponse>('/api/auth/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
  saveToken(resp.access_token);
}

/** Новый пароль для телефона: старый перестаёт работать, новый виден только сейчас. */
export async function issueCarddavPassword(): Promise<CarddavPassword> {
  return apiFetch<CarddavPassword>('/api/auth/carddav-password', { method: 'POST' });
}

export async function revokeCarddavPassword(): Promise<void> {
  return apiFetch<void>('/api/auth/carddav-password', { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Contacts
// ---------------------------------------------------------------------------

export type ContactSort = 'last_interaction' | 'name' | 'created' | 'importance';

export interface ListParams {
  q?: string;
  category?: string;
  priority?: string;
  tag?: string;
  group_id?: string;
  has_location?: boolean;
  sort?: ContactSort;
  skip?: number;
  limit?: number;
}

export async function getContacts(params: ListParams = {}): Promise<Contact[]> {
  const qs = new URLSearchParams();
  if (params.q) qs.set('q', params.q);
  if (params.category) qs.set('category', params.category);
  if (params.priority) qs.set('priority', params.priority);
  if (params.tag) qs.set('tag', params.tag);
  if (params.group_id) qs.set('group_id', params.group_id);
  if (params.has_location !== undefined) qs.set('has_location', String(params.has_location));
  if (params.sort) qs.set('sort', params.sort);
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

// ---------------------------------------------------------------------------
// Телефон (CardDAV)
// ---------------------------------------------------------------------------

export interface CarddavStatus {
  enabled: boolean;
  username: string;
  path: string;
}

// ---------------------------------------------------------------------------
// Вложения к контактам (файлы — в S3 / MinIO, скачивание — через backend)
// ---------------------------------------------------------------------------

export interface Attachment {
  id: string;
  contact_id: string;
  file_name: string;
  size: number;
  content_type: string;
  created_at: string;
}

export interface AttachmentUsage {
  used: number;
  quota: number;
  max_file_size: number;
}

export const attachmentUsageKey = '/api/attachments/usage';

export function attachmentsKey(contactId: string): string {
  return `/api/contacts/${contactId}/attachments`;
}

/** Загрузка через XMLHttpRequest: у fetch нет прогресса отправки. onProgress — доля 0…1. */
export function uploadAttachment(
  contactId: string,
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<Attachment> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append('file', file);
    xhr.open('POST', `${API_URL}${attachmentsKey(contactId)}`);
    const token = getToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new ApiError(0, 'Нет связи с сервером'));
    xhr.onload = () => {
      if (xhr.status === 401) {
        clearToken();
        reject(new ApiError(401, 'Не авторизован'));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        void errorMessage(new Response(xhr.responseText, { status: xhr.status })).then((msg) =>
          reject(new ApiError(xhr.status, msg || 'Не удалось загрузить файл')),
        );
        return;
      }
      resolve(JSON.parse(xhr.responseText) as Attachment);
    };
    xhr.send(form);
  });
}

/** Скачать файл: ссылка без токена не сработает, поэтому — fetch с Bearer и сохранение blob. */
export async function downloadAttachment(attachment: Attachment): Promise<void> {
  const token = getToken();
  const resp = await fetch(`${API_URL}${attachmentsKey(attachment.contact_id)}/${attachment.id}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new ApiError(resp.status, await errorMessage(resp));
  const url = URL.createObjectURL(await resp.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = attachment.file_name;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

export function deleteAttachment(contactId: string, attachmentId: string): Promise<void> {
  return apiFetch<void>(`${attachmentsKey(contactId)}/${attachmentId}`, { method: 'DELETE' });
}

// ---------------------------------------------------------------------------
// Календарь (Sprint 7)
// ---------------------------------------------------------------------------

export interface Attendee {
  email: string;
  name: string;
  phone: string;
  response: string;
}

export interface EventQuestion {
  id: string;
  contact_id: string;
  contact_name: string;
  text: string;
}

export interface CalendarEvent {
  id: string;
  title: string;
  /** ISO в UTC; для «весь день» — полночь первого дня и дня после последнего */
  start: string;
  end: string;
  all_day: boolean;
  timezone: string;
  location: string;
  description: string;
  attendees: Attendee[];
  contact_ids: string[];
  contacts: { id: string; name: string }[];
  /** Открытые вопросы «на встрече» к привязанным людям */
  questions: EventQuestion[];
  push_questions: boolean;
  source: 'crm' | 'microsoft' | 'google';
  connection_id: string | null;
  external_id: string | null;
  web_link: string;
  created_at: string;
  updated_at: string;
}

export interface EventInput {
  title?: string;
  start?: string;
  end?: string;
  all_day?: boolean;
  timezone?: string;
  location?: string;
  description?: string;
  contact_ids?: string[];
  push_questions?: boolean;
  /** Только при создании: сразу записать в календарь подключения */
  connection_id?: string | null;
}

/** Состояние календаря у подключения (поля появились в Sprint 7). */
export interface CalendarConnection extends SyncConnection {
  calendar_access: boolean;
  calendar_last_sync: string | null;
}

/** Ключ SWR списка событий за период (и/или с одним человеком). */
export function eventsKey(params: { start?: Date; end?: Date; contactId?: string }): string {
  const qs = new URLSearchParams();
  if (params.start) qs.set('start', params.start.toISOString());
  if (params.end) qs.set('end', params.end.toISOString());
  if (params.contactId) qs.set('contact_id', params.contactId);
  return `/api/calendar/events?${qs.toString()}`;
}

export function createEvent(data: EventInput): Promise<CalendarEvent> {
  return apiFetch<CalendarEvent>('/api/calendar/events', { method: 'POST', body: JSON.stringify(data) });
}

export function updateEvent(id: string, data: EventInput): Promise<CalendarEvent> {
  return apiFetch<CalendarEvent>(`/api/calendar/events/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export function deleteEvent(id: string): Promise<void> {
  return apiFetch<void>(`/api/calendar/events/${id}`, { method: 'DELETE' });
}

/** Записать событие в календарь провайдера (или перезаписать там — обновить вопросы). */
export function pushEvent(id: string, connectionId: string | null = null): Promise<CalendarEvent> {
  return apiFetch<CalendarEvent>(`/api/calendar/events/${id}/push`, {
    method: 'POST',
    body: JSON.stringify({ connection_id: connectionId }),
  });
}

export function triggerCalendarSync(connectionId: string): Promise<SyncLogEntry> {
  return apiFetch<SyncLogEntry>(`/api/sync/calendar/${connectionId}`, { method: 'POST' });
}

export function updateConnection(
  id: string,
  data: { sync_contacts?: boolean; sync_calendar?: boolean },
): Promise<CalendarConnection> {
  return apiFetch<CalendarConnection>(`/api/sync/connections/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
}

/** Переподключить аккаунт (например, выдать доступ к календарю) — настройки подключения сохраняются. */
export function reconnectProvider(
  provider: 'microsoft' | 'google',
  connectionId: string,
): Promise<{ authorize_url: string; state: string }> {
  return apiFetch(`/api/sync/connect/${provider}?connection_id=${encodeURIComponent(connectionId)}`, {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// ИИ-помощник: задачи в очереди (быстрый захват и «спроси»)
// ---------------------------------------------------------------------------

export type AssistantJobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled' | 'applied';

export interface ContactRef {
  id: string;
  name: string;
  company?: string;
  city?: string;
}

export type CaptureAction = { index: number; error?: string } & (
  | { type: 'update_field'; key: string; label: string; old: string; new: string }
  | { type: 'answer_question'; question_id: string; question: string; answer: string }
  | { type: 'add_question'; text: string }
  | { type: 'add_note'; text: string }
  | { type: 'add_phone'; value: string }
  | { type: 'add_email'; value: string }
  | { type: 'create_contact'; name: string }
  | { type: 'delete_contact'; name: string }
);

/** Как помощник искал: слова поиска, найденные контакты, шаги модели со временем. */
export interface JobTrace {
  intent?: 'capture' | 'question' | 'delete';
  /** «Спросить»: слова поиска; «Записать»: номера и почта из записи */
  terms?: string[];
  search?: string[];
  person?: { mention: string; first_name: string; last_name: string };
  /** command — модель не нашла имя, оно взято из команды «создай контакт …» */
  name_source?: 'command';
  /** search — нашлись карточки; recent — поиск пуст, модель видела последние контакты */
  source?: 'search' | 'recent';
  found?: { id: string; name: string }[];
  context?: { id: string; name: string }[];
  llm?: { step: string; ms: number }[];
  total_ms?: number;
}

export interface CaptureResult {
  text: string;
  contact_id: string | null;
  candidates: ContactRef[];
  new_contact: { first_name: string; last_name: string } | null;
  actions: CaptureAction[];
  /** Запись похожа на вопрос: модель не вызывалась, интерфейс предлагает «Спросить» */
  suggest_ask?: boolean;
  /** delete — запись была командой удаления: показываем найденные карточки и просим подтверждение */
  mode?: 'delete';
  /** Имя из команды удаления (для сообщения «не нашёл») */
  target_name?: string;
  trace?: JobTrace;
}

export interface AskResult {
  question: string;
  answer: string;
  contacts: ContactRef[];
  trace?: JobTrace;
}

export interface AssistantJob<R = CaptureResult | AskResult> {
  id: string;
  kind: 'capture' | 'ask' | 'chat' | 'dossier';
  status: AssistantJobStatus;
  position: number | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  result: R | null;
  error: string | null;
}

export interface ApplyResult {
  contact_id: string;
  created_contact: ContactRef | null;
  deleted_contact?: { id: string; name: string } | null;
  results: { index: number; ok: boolean; error?: string }[];
}

export interface AssistantInfo {
  model: string;
  fallback: string | null;
  concurrency: number;
  max_queued: number;
}

export const assistantInfoKey = '/api/assistant/info';

export function assistantJobKey(id: string): string {
  return `/api/assistant/jobs/${id}`;
}

/** force — записать, даже если текст похож на вопрос. */
export function startCapture(text: string, force = false): Promise<AssistantJob> {
  return apiFetch<AssistantJob>('/api/assistant/capture', { method: 'POST', body: JSON.stringify({ text, force }) });
}

export function startAsk(question: string): Promise<AssistantJob> {
  return apiFetch<AssistantJob>('/api/assistant/ask', { method: 'POST', body: JSON.stringify({ question }) });
}

export function cancelAssistantJob(id: string): Promise<AssistantJob> {
  return apiFetch<AssistantJob>(assistantJobKey(id), { method: 'DELETE' });
}

export function applyCapture(
  id: string,
  actions: number[],
  contactId: string | null,
  newName?: string,
): Promise<ApplyResult> {
  return apiFetch<ApplyResult>(`${assistantJobKey(id)}/apply`, {
    method: 'POST',
    body: JSON.stringify({ actions, contact_id: contactId, new_name: newName || null }),
  });
}
