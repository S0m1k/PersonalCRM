import { cn, initials } from '@/lib/utils';

// Тёплые пастельные заливки: золото, олива, терракота, шалфей, коричневый
const WARM_FILLS = ['bg-tag-yellow', 'bg-olive-200', 'bg-tag-orange', 'bg-tag-green', 'bg-tag-brown'];

function fillFor(seed: string): string {
  let hash = 0;
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return WARM_FILLS[Math.abs(hash) % WARM_FILLS.length];
}

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
        'inline-flex shrink-0 select-none items-center justify-center rounded-full font-semibold text-fg',
        fillFor(name),
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
