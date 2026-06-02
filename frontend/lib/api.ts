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
}

export type ContactUpdate = Partial<ContactCreate>;

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

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
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
    // Перенаправление выполняется в компоненте
    throw new ApiError(401, 'Не авторизован');
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new ApiError(resp.status, text);
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
