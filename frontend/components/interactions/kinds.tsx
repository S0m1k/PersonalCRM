import { CircleDot, Mail, MessageSquare, Phone, StickyNote, Users, type LucideIcon } from 'lucide-react';
import type { InteractionKind } from '@/lib/api-crm';
import { cn } from '@/lib/utils';

interface KindMeta {
  label: string;
  icon: LucideIcon;
  /** классы плитки иконки: заливка + цвет */
  tone: string;
}

const NEUTRAL = 'bg-hover text-muted';

export const INTERACTION_KINDS: Record<InteractionKind, KindMeta> = {
  note: { label: 'Заметка', icon: StickyNote, tone: 'bg-crm-note/15 text-crm-note' },
  email: { label: 'Письмо', icon: Mail, tone: 'bg-crm-email/15 text-crm-email' },
  meeting: { label: 'Встреча', icon: Users, tone: 'bg-crm-meeting/15 text-crm-meeting' },
  call: { label: 'Звонок', icon: Phone, tone: NEUTRAL },
  message: { label: 'Сообщение', icon: MessageSquare, tone: NEUTRAL },
  other: { label: 'Другое', icon: CircleDot, tone: NEUTRAL },
};

export const INTERACTION_KIND_ORDER: InteractionKind[] = ['note', 'meeting', 'call', 'message', 'email', 'other'];

export function kindLabel(kind: InteractionKind): string {
  return INTERACTION_KINDS[kind].label;
}

/** Круглая плитка с иконкой типа взаимодействия. */
export function InteractionKindIcon({ kind, className }: { kind: InteractionKind; className?: string }) {
  const { icon: Icon, tone, label } = INTERACTION_KINDS[kind];
  return (
    <span
      role="img"
      aria-label={label}
      className={cn('inline-flex size-8 shrink-0 items-center justify-center rounded-full [&_svg]:size-4', tone, className)}
    >
      <Icon aria-hidden />
    </span>
  );
}
