'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { Cake, Search, SearchX } from 'lucide-react';
import { getContacts, type Contact } from '@/lib/api';
import { upcomingBirthdays, type BirthdayEntry } from '@/lib/birthdays';
import { fullName, plural } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { EmptyState, Page, PageHeader, SectionTitle, Skeleton } from '@/components/app/page';
import { Tag } from '@/components/ui/tag';

const PAGE = 200;
const MAX_PAGES = 25;

/** Все контакты с днём рождения: страницами по 200, пока не кончатся. */
async function loadWithBirthday(): Promise<Contact[]> {
  const all: Contact[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const chunk = await getContacts({ has_birthday: true, sort: 'name', limit: PAGE, skip: page * PAGE });
    all.push(...chunk);
    if (chunk.length < PAGE) break;
  }
  return all;
}

export default function BirthdaysPage() {
  const { data: contacts, isLoading } = useSWR('birthdays:contacts', loadWithBirthday);
  const [query, setQuery] = useState('');

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const entries = upcomingBirthdays(contacts ?? [], new Date()).filter((e) => !q || fullName(e.contact).toLowerCase().includes(q));
    const byMonth = new Map<string, BirthdayEntry[]>();
    for (const e of entries) byMonth.set(e.monthLabel, [...(byMonth.get(e.monthLabel) ?? []), e]);
    return [...byMonth.entries()];
  }, [contacts, query]);

  const total = contacts?.length ?? 0;

  return (
    <Page>
      <PageHeader
        icon={Cake}
        title="Дни рождения"
        description={total ? `${total} ${plural(total, 'человек', 'человека', 'человек')} с днём рождения в ближайшие 12 месяцев` : 'Ближайшие дни рождения по месяцам'}
      />

      <label className="relative mb-6 flex h-9 max-w-sm items-center">
        <Search className="pointer-events-none absolute left-3 size-4 text-faint" aria-hidden />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по имени"
          aria-label="Поиск по имени"
          className="h-full w-full rounded-lg border border-line bg-surface pl-9 pr-3 text-sm outline-none placeholder:text-faint focus-visible:border-accent"
        />
      </label>

      {isLoading && (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      )}

      {!isLoading && total === 0 && (
        <EmptyState icon={Cake} title="Дней рождения пока нет">
          Добавьте дату рождения в карточке контакта — здесь появятся ближайшие.
        </EmptyState>
      )}

      {!isLoading && total > 0 && groups.length === 0 && (
        <EmptyState icon={SearchX} title="Никого не нашлось">
          Попробуйте другое имя.
        </EmptyState>
      )}

      <div className="flex flex-col gap-8">
        {groups.map(([month, entries]) => (
          <section key={month} aria-label={month}>
            <SectionTitle aside={<span className="text-xs text-faint tabular">{entries.length}</span>}>{month}</SectionTitle>
            <ul>
              {entries.map((e) => (
                <li key={e.contact.id}>
                  <Link
                    href={`/contacts/${e.contact.id}`}
                    className="flex items-center gap-3 border-b border-line px-1 py-2 transition-colors hover:bg-hover/60"
                  >
                    <Avatar name={fullName(e.contact) || 'Без имени'} size="lg" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{fullName(e.contact) || 'Без имени'}</span>
                      <span className="block truncate text-xs text-muted">
                        {e.dateLabel}
                        {e.turns !== null && ` · исполнится ${e.turns}`}
                      </span>
                    </span>
                    <Tag color={e.daysUntil === 0 ? 'orange' : e.daysUntil <= 7 ? 'yellow' : 'gray'}>{e.untilLabel}</Tag>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </Page>
  );
}
