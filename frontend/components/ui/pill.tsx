import { forwardRef, type ButtonHTMLAttributes } from 'react';
import type { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PillProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: LucideIcon;
  /** Выбрано/заполнено: подсвечивает пилюлю акцентом */
  isActive?: boolean;
}

/** Пилюля-действие («Приоритет», «Частота», «Добавить теги»): rounded-full, тонкая граница, иконка 14px. */
export const Pill = forwardRef<HTMLButtonElement, PillProps>(function Pill(
  { icon: Icon, isActive = false, className, children, type = 'button', ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-[13px] font-medium transition-colors [&_svg]:size-3.5 [&_svg]:shrink-0',
        isActive
          ? 'border-accent-300 bg-accent-50 text-accent-700 dark:border-accent-700 dark:bg-accent-950 dark:text-accent-200'
          : 'border-line bg-surface text-muted hover:bg-hover hover:text-fg',
        className,
      )}
      {...props}
    >
      {Icon && <Icon aria-hidden />}
      {children}
    </button>
  );
});
