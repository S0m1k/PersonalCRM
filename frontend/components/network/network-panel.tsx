'use client';

import type { ReactNode } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { SectionLabel } from '@/components/ui/section-label';

interface Props {
  title: string;
  /** «42 контакта · 5 групп» */
  subtitle?: ReactNode;
  search?: { value: string; onChange: (value: string) => void; placeholder: string };
  help: string[];
  children?: ReactNode;
}

/** Плавающая правая панель экрана «Сеть»: заголовок, счётчики, поиск, действия, «Как пользоваться». */
export function NetworkPanel({ title, subtitle, search, help, children }: Props) {
  return (
    <aside className="absolute right-3 top-3 z-10 flex max-h-[calc(100%-1.5rem)] w-72 max-w-[calc(100%-1.5rem)] flex-col gap-3 overflow-auto rounded-2xl border border-line bg-surface/95 p-4 shadow-lg backdrop-blur">
      <div>
        <h2 className="font-display text-xl font-semibold leading-tight">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-muted">{subtitle}</p>}
      </div>
      {search && (
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden />
          <Input
            aria-label={search.placeholder}
            placeholder={search.placeholder}
            value={search.value}
            onChange={(e) => search.onChange(e.target.value)}
            className="h-8 pl-8"
          />
        </div>
      )}
      {children}
      <div>
        <SectionLabel>Как пользоваться</SectionLabel>
        <ul className="mt-1.5 list-disc space-y-1 pl-4 text-xs text-muted">
          {help.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
