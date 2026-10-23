import { cn, colorFor, initials } from '@/lib/utils';

const BG: Record<string, string> = {
  orange: 'bg-tag-orange',
  yellow: 'bg-tag-yellow',
  green: 'bg-tag-green',
  blue: 'bg-tag-blue',
  purple: 'bg-tag-purple',
  pink: 'bg-tag-pink',
  red: 'bg-tag-red',
  brown: 'bg-tag-brown',
};

type Props = {
  name: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
};

const SIZES = {
  sm: 'size-5 text-[9px]',
  md: 'size-7 text-[11px]',
  lg: 'size-9 text-[13px]',
  xl: 'size-[72px] text-2xl',
};

/** Кружок с инициалами; цвет стабилен для имени. */
export function Avatar({ name, size = 'md', className }: Props) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-fg/80',
        BG[colorFor(name)],
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
