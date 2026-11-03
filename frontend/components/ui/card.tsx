import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { SectionLabel } from './section-label';

export { SectionLabel };

/** Карточка-панель: скруглённая, с тонкой границей и мягкой тенью. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('rounded-2xl border border-line bg-surface p-4 shadow-xs', className)} {...props} />;
}

type CardHeaderProps = {
  /** Подпись секции (рендерится в верхнем регистре) */
  label: ReactNode;
  /** Действие справа: обычно CardAction («ДОБАВИТЬ») или свой узел */
  action?: ReactNode;
  className?: string;
};

export function CardHeader({ label, action, className }: CardHeaderProps) {
  return (
    <div className={cn('mb-3 flex items-center justify-between gap-2', className)}>
      <SectionLabel>{label}</SectionLabel>
      {action}
    </div>
  );
}

/** Действие в шапке карточки: 11px, UPPERCASE, цвет акцента. */
export function CardAction({ className, type = 'button', ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type={type}
      className={cn(
        'rounded text-[11px] font-semibold uppercase leading-none tracking-[0.08em] text-accent transition-colors hover:text-accent-hover',
        className,
      )}
      {...props}
    />
  );
}
