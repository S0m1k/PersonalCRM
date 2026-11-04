import { CalendarDays, Mail, MessageCircle, MoreHorizontal, Phone, StickyNote, type LucideIcon } from 'lucide-react';
import type { InteractionKind } from '@/lib/api-crm';

/** Тип взаимодействия: подпись, иконка и цвет (классы написаны целиком — для Tailwind JIT). */
export const KIND_META: Record<InteractionKind, { label: string; icon: LucideIcon; tone: string }> = {
  note: { label: 'Заметка', icon: StickyNote, tone: 'bg-crm-note/15 text-crm-note' },
  call: { label: 'Звонок', icon: Phone, tone: 'bg-crm-strong/15 text-crm-strong' },
  meeting: { label: 'Встреча', icon: CalendarDays, tone: 'bg-crm-meeting/15 text-crm-meeting' },
  message: { label: 'Сообщение', icon: MessageCircle, tone: 'bg-crm-group/15 text-crm-group' },
  email: { label: 'Письмо', icon: Mail, tone: 'bg-crm-email/15 text-crm-email' },
  other: { label: 'Другое', icon: MoreHorizontal, tone: 'bg-hover text-muted' },
};

export const KIND_ORDER = Object.keys(KIND_META) as InteractionKind[];

/** ISO-время → значение для <input type="datetime-local"> в локальной зоне. */
export function toLocalInput(iso: string | Date): string {
  const d = typeof iso === 'string' ? new Date(iso) : iso;
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

const MONTH_FMT = new Intl.DateTimeFormat('ru-RU', { month: 'long', year: 'numeric' });
const DATE_TIME_FMT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

export function monthTitle(iso: string): string {
  const title = MONTH_FMT.format(new Date(iso));
  return title.charAt(0).toUpperCase() + title.slice(1);
}

export function formatWhen(iso: string): string {
  return DATE_TIME_FMT.format(new Date(iso));
}
