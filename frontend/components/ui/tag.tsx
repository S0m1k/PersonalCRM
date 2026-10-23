import type { HTMLAttributes } from 'react';
import { cn, type TagColor } from '@/lib/utils';

const COLORS: Record<TagColor, string> = {
  gray: 'bg-tag-gray',
  brown: 'bg-tag-brown',
  orange: 'bg-tag-orange',
  yellow: 'bg-tag-yellow',
  green: 'bg-tag-green',
  blue: 'bg-tag-blue',
  purple: 'bg-tag-purple',
  pink: 'bg-tag-pink',
  red: 'bg-tag-red',
};

interface TagProps extends HTMLAttributes<HTMLSpanElement> {
  color?: TagColor;
}

/** Плашка-метка, как опции select-свойства в Notion. */
export function Tag({ color = 'gray', className, ...props }: TagProps) {
  return (
    <span
      className={cn(
        'inline-flex h-5 max-w-full items-center gap-1 truncate rounded-[3px] px-1.5 text-[12.5px] leading-none text-fg',
        COLORS[color],
        className,
      )}
      {...props}
    />
  );
}

export function Kbd({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[4px] border border-line bg-surface px-1 font-sans text-[11px] font-medium text-muted shadow-[0_1px_0_rgb(var(--line))]',
        className,
      )}
      {...props}
    />
  );
}
