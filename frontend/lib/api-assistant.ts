/**
 * API чатов помощника и досье контакта (/api/assistant/chats, /api/assistant/dossier).
 * Задачи (опрос, отмена, применение предпросмотра) — в lib/api.ts: assistantJobKey и др.
 */

import { ApiError, apiFetch, type ApplyResult, type AssistantJob, type CaptureResult, type ContactRef } from './api';

// ---------------------------------------------------------------------------
// Блоки ответа помощника
// ---------------------------------------------------------------------------

export interface TextBlock {
  type: 'text';
  text: string;
}

export interface ChartPoint {
  x: string | number;
  y: number;
}

export interface ChartSeries {
  name: string;
  points: ChartPoint[];
}

export interface ChartBlock {
  type: 'chart';
  chart: 'bar' | 'line' | 'pie';
  title: string;
  x_label: string;
  y_label: string;
  series: ChartSeries[];
}

export interface TableColumn {
  key: string;
  label: string;
}

export interface TableBlock {
  type: 'table';
  title: string;
  columns: TableColumn[];
  rows: Record<string, string | number | null>[];
}

export interface ContactsBlock {
  type: 'contacts';
  contact_ids: string[];
  contacts: ContactRef[];
}

export interface CapturePreviewBlock {
  type: 'capture_preview';
  job_id: string;
  result: CaptureResult;
  applied: ApplyResult | null;
}

export type Block = TextBlock | ChartBlock | TableBlock | ContactsBlock | CapturePreviewBlock;

// ---------------------------------------------------------------------------
// Чаты
// ---------------------------------------------------------------------------

export interface Chat {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  archived: boolean;
  summary: string;
  summary_upto: number;
}

export interface ChatMessage {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  blocks: Block[];
  job_id: string | null;
  created_at: string;
}

export interface MessagePage {
  items: ChatMessage[];
  /** Есть более ранние сообщения: запросить before=<id первого элемента> */
  has_more: boolean;
}

/** Трасса ответа чата: путь (аналитика / вопрос / запись), вызванные инструменты, контекст. */
export interface ChatTrace {
  route?: 'analytics' | 'ask' | 'capture';
  tools?: { tool: string; params: Record<string, unknown>; error?: string }[];
  history?: { messages_total: number; in_context: number; summary_upto: number; summarised: boolean };
  llm?: { step: string; ms: number }[];
  total_ms?: number;
}

export interface ChatJobResult {
  chat_id: string;
  message_id: string;
  blocks: Block[];
  capture?: CaptureResult;
  trace?: ChatTrace;
}

export interface SentMessage extends ChatMessage {
  job: AssistantJob<ChatJobResult>;
}

export const chatsKey = '/api/assistant/chats';

export function chatMessagesKey(chatId: string): string {
  return `${chatsKey}/${chatId}/messages`;
}

export function createChat(title?: string): Promise<Chat> {
  return apiFetch<Chat>(chatsKey, { method: 'POST', body: JSON.stringify({ title: title ?? null }) });
}

export function renameChat(chatId: string, title: string): Promise<Chat> {
  return apiFetch<Chat>(`${chatsKey}/${chatId}`, { method: 'PATCH', body: JSON.stringify({ title }) });
}

export function deleteChat(chatId: string): Promise<void> {
  return apiFetch<void>(`${chatsKey}/${chatId}`, { method: 'DELETE' });
}

export function sendChatMessage(chatId: string, text: string): Promise<SentMessage> {
  return apiFetch<SentMessage>(chatMessagesKey(chatId), { method: 'POST', body: JSON.stringify({ text }) });
}

/** Более ранние сообщения: до сообщения with id = before. */
export function fetchOlderMessages(chatId: string, before: string, limit = 50): Promise<MessagePage> {
  return apiFetch<MessagePage>(`${chatMessagesKey(chatId)}?limit=${limit}&before=${encodeURIComponent(before)}`);
}

// ---------------------------------------------------------------------------
// Досье контакта
// ---------------------------------------------------------------------------

export interface Dossier {
  contact_id: string;
  text: string;
  generated_at: string;
  model: string;
}

export function dossierKey(contactId: string): string {
  return `/api/assistant/dossier/${contactId}`;
}

/** Запустить составление досье: задача в очереди, опрос — assistantJobKey(job.id). */
export function startDossier(contactId: string): Promise<AssistantJob<Dossier>> {
  return apiFetch<AssistantJob<Dossier>>(dossierKey(contactId), { method: 'POST' });
}

/** Последнее досье или null, если его ещё не составляли. */
export async function getDossier(contactId: string): Promise<Dossier | null> {
  try {
    return await apiFetch<Dossier>(dossierKey(contactId));
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}
