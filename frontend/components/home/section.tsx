import Link from 'next/link';
import type { ReactNode } from 'react';

type Props = {
  title: string;
  /** Ссылка справа («Все →»); без неё — только заголовок */
  href?: string;
  linkLabel?: string;
  children: ReactNode;
};

/** Секция главной: заголовок 13px medium, опциональная ссылка справа, содержимое. */
export function HomeSection({ title, href, linkLabel = 'Все →', children }: Props) {
  return (
    <section aria-label={title}>
      <div className="mb-2 flex items-center justify-between border-b border-line pb-1.5">
        <h2 className="text-[13px] font-medium">{title}</h2>
        {href && (
          <Link href={href} className="text-xs text-muted hover:text-fg">
            {linkLabel}
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}
