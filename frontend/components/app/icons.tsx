/**
 * SVG-иконки приложения: иконки шаблонов карточек (имена хранятся в базе) и знаки сервисов.
 */

import {
  Briefcase,
  Building2,
  Coins,
  Dumbbell,
  FileText,
  Gem,
  GraduationCap,
  Handshake,
  Heart,
  House,
  IdCard,
  Palette,
  Plane,
  Rocket,
  Scale,
  Smile,
  Star,
  Stethoscope,
  Users,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';

/** Тот же набор, что TEMPLATE_ICONS в backend/app/models/template.py */
export const TEMPLATE_ICONS: Record<string, LucideIcon> = {
  'file-text': FileText,
  briefcase: Briefcase,
  handshake: Handshake,
  smile: Smile,
  house: House,
  'id-card': IdCard,
  heart: Heart,
  star: Star,
  users: Users,
  building: Building2,
  'graduation-cap': GraduationCap,
  stethoscope: Stethoscope,
  wrench: Wrench,
  plane: Plane,
  gem: Gem,
  coins: Coins,
  rocket: Rocket,
  scale: Scale,
  palette: Palette,
  dumbbell: Dumbbell,
};

export function TemplateIcon({ name, className }: { name: string; className?: string }) {
  const Icon = TEMPLATE_ICONS[name] ?? FileText;
  return <Icon aria-hidden className={cn('size-3.5 shrink-0', className)} />;
}

/** Большая плитка с иконкой в заголовке страницы. */
export function IconTile({ icon: Icon, size = 'lg' }: { icon: LucideIcon; size?: 'md' | 'lg' }) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-flex items-center justify-center rounded-xl border border-line bg-sidebar text-muted shadow-xs',
        size === 'lg' ? 'size-12 sm:size-14' : 'size-10',
      )}
    >
      <Icon className={size === 'lg' ? 'size-6 sm:size-7' : 'size-5'} strokeWidth={1.6} />
    </span>
  );
}

export function GoogleMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" aria-hidden className={cn('size-6', className)}>
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.3-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.8 1.2 7.9 3.1l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-7.9l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C37 39.2 44 34 44 24c0-1.2-.1-2.3-.4-3.5z" />
    </svg>
  );
}

export function MicrosoftMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cn('size-6', className)}>
      <rect x="2" y="2" width="9.5" height="9.5" fill="#F25022" />
      <rect x="12.5" y="2" width="9.5" height="9.5" fill="#7FBA00" />
      <rect x="2" y="12.5" width="9.5" height="9.5" fill="#00A4EF" />
      <rect x="12.5" y="12.5" width="9.5" height="9.5" fill="#FFB900" />
    </svg>
  );
}
