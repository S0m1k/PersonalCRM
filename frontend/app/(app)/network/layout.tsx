'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BarChart3, Network } from 'lucide-react';
import { Page, PageHeader } from '@/components/app/page';
import { cn } from '@/lib/utils';

const VIEWS = [
  { href: '/network', label: 'Вселенная' },
  { href: '/network/groups', label: 'Группы' },
  { href: '/network/related', label: 'Связи' },
  { href: '/network/companies', label: 'Компании' },
];

export default function NetworkLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isInsights = pathname.startsWith('/network/insights');

  return (
    <Page wide>
      <PageHeader
        icon={Network}
        title={isInsights ? 'Инсайты сети' : 'Сеть'}
        actions={
          isInsights ? (
            <Link href="/network" className="text-sm text-accent hover:text-accent-hover">К графу</Link>
          ) : (
            <Link href="/network/insights" className="inline-flex items-center gap-1.5 text-sm text-accent hover:text-accent-hover">
              <BarChart3 className="size-4" aria-hidden />
              Инсайты
            </Link>
          )
        }
      />
      {!isInsights && (
        <nav aria-label="Вид сети" className="mb-4 inline-flex rounded-full border border-line bg-surface p-0.5">
          {VIEWS.map((view) => {
            const isActive = pathname === view.href || pathname === `${view.href}/`;
            return (
              <Link
                key={view.href}
                href={view.href}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'rounded-full px-4 py-1 text-sm font-medium transition-colors',
                  isActive ? 'bg-accent text-accent-fg shadow-xs' : 'text-muted hover:text-fg',
                )}
              >
                {view.label}
              </Link>
            );
          })}
        </nav>
      )}
      {children}
    </Page>
  );
}
