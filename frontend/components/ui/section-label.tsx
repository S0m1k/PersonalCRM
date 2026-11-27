import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

/** Подпись секции: 11px, UPPERCASE, приглушённая («ОПИСАНИЕ», «ДОБАВЛЕН» как в Dex). */
export function SectionLabel({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn('text-[11px] font-semibold uppercase leading-[1.35] tracking-[0.08em] text-muted', className)}
      {...props}
    />
  );
}
