import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { IconTile } from './icons';

/** Колонка страницы в духе Notion: широкие поля, контент по центру. */
export function Page({ children, wide = false, className }: { children: ReactNode; wide?: boolean; className?: string }) {
  return (
    <div className={cn('mx-auto w-full px-4 pb-24 pt-8 sm:px-12 sm:pt-14 lg:px-24', wide ? 'max-w-[1200px]' : 'max-w-[900px]', className)}>
      {children}
    </div>
  );
}

type HeaderProps = {
  icon?: LucideIcon;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
};

export function PageHeader({ icon, title, description, actions }: HeaderProps) {
  return (
    <header className="mb-8 animate-fade-up">
      {icon && (
        <div className="mb-4">
          <IconTile icon={icon} />
        </div>
      )}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-display text-title">{title}</h1>
        {actions && <div className="flex items-center gap-1.5 pb-1">{actions}</div>}
      </div>
      {description && <p className="mt-2 max-w-prose text-[15px] text-muted">{description}</p>}
    </header>
  );
}

/** Заголовок секции: маленький, приглушённый, с линией. */
export function SectionTitle({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-2 flex items-center justify-between border-b border-line pb-1.5">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">{children}</h2>
      {aside}
    </div>
  );
}

export function EmptyState({ icon, title, children }: { icon: LucideIcon; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-line-strong px-6 py-10 text-center">
      <div className="mb-3">
        <IconTile icon={icon} size="md" />
      </div>
      <div className="text-sm font-medium">{title}</div>
      {children && <div className="mt-1 max-w-sm text-sm text-muted">{children}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded bg-hover', className)} />;
}
