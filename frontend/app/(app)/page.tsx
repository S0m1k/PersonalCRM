'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { ArrowUpRight, CalendarDays, Plus, Search } from 'lucide-react';
import { homeKey, type HomeSummary, type UpcomingBirthday } from '@/lib/api';
import { formatDate, plural } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { useAppActions } from '@/components/app/app-shell';
import { EmptyState, Page, SectionTitle, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Kbd, Tag } from '@/components/ui/tag';

const TODAY_FMT = new Intl.DateTimeFormat('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return 'Доброй ночи';
  if (hour < 12) return 'Доброе утро';
  if (hour < 18) return 'Добрый день';
  return 'Добрый вечер';
}

export default function HomePage() {
  const { openSearch, newContact } = useAppActions();
  const { data, isLoading } = useSWR<HomeSummary>(homeKey());

  return (
    <Page>
      <header className="mb-8 animate-fade-up">
        <p className="text-sm text-muted first-letter:uppercase">{TODAY_FMT.format(new Date())}</p>
        <h1 className="mt-1 text-title">{greeting()}</h1>
      </header>

      <button
        type="button"
        onClick={openSearch}
        className="group mb-10 flex h-12 w-full items-center gap-3 rounded-lg border border-line bg-surface px-4 text-left shadow-[0_1px_2px_rgb(0_0_0/0.04)] transition-all hover:border-faint/60 hover:shadow-pop"
      >
        <Search className="size-5 text-faint" />
        <span className="flex-1 text-[15px] text-faint">Найти человека, компанию, телефон…</span>
        <Kbd>Ctrl K</Kbd>
      </button>

      <div className="grid gap-x-10 gap-y-10 md:grid-cols-[1.4fr_1fr]">
        <section>
          <SectionTitle
            aside={
              <Link href="/questions" className="flex items-center gap-0.5 text-xs text-muted hover:text-fg">
                Все вопросы <ArrowUpRight className="size-3.5" />
              </Link>
            }
          >
            Хотел спросить
          </SectionTitle>
          {isLoading ? (
            <ListSkeleton />
          ) : data?.open_questions.length ? (
            <ul className="flex flex-col">
              {data.open_questions.map((q) => (
                <li key={q.id}>
                  <Link
                    href={`/contacts/${q.contact_id}?tab=questions`}
                    className="-mx-2 flex items-start gap-3 rounded px-2 py-2 transition-colors hover:bg-hover"
                  >
                    <span className="mt-[3px] size-3.5 shrink-0 rounded-[3px] border-[1.5px] border-faint" aria-hidden />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm">{q.text}</span>
                      <span className="text-xs text-muted">{q.contact_name}</span>
                    </span>
                    {q.ask_at === 'next_meeting' && <Tag color="blue">на встрече</Tag>}
                    {q.ask_at && q.ask_at !== 'next_meeting' && <Tag color="yellow">{formatDate(q.ask_at, false)}</Tag>}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState icon="❓" title="Открытых вопросов нет">
              В карточке человека во вкладке «Вопросы» можно записать, что хотите у него узнать.
            </EmptyState>
          )}
        </section>

        <div className="flex flex-col gap-10">
          <section>
            <SectionTitle>Сегодня</SectionTitle>
            <div className="flex items-center gap-3 rounded-md bg-sidebar px-3 py-3 text-sm text-muted">
              <CalendarDays className="size-5 shrink-0 text-faint" />
              Встречи и задачи из календаря появятся здесь на следующем этапе.
            </div>
          </section>

          <section>
            <SectionTitle>Дни рождения</SectionTitle>
            {isLoading ? (
              <ListSkeleton rows={2} />
            ) : data?.birthdays.length ? (
              <ul className="flex flex-col">
                {data.birthdays.map((b) => (
                  <BirthdayRow key={b.contact_id} birthday={b} />
                ))}
              </ul>
            ) : (
              <p className="py-2 text-sm text-faint">В ближайшие две недели — ни у кого.</p>
            )}
          </section>
        </div>

        <section className="md:col-span-2">
          <SectionTitle
            aside={
              <Button variant="ghost" size="sm" onClick={() => newContact()}>
                <Plus /> Новый
              </Button>
            }
          >
            Недавние
          </SectionTitle>
          {isLoading ? (
            <ListSkeleton rows={2} />
          ) : data?.recent.length ? (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {data.recent.map((c) => (
                <Link
                  key={c.id}
                  href={`/contacts/${c.id}`}
                  className="group flex flex-col gap-3 rounded-md border border-line p-3 transition-all hover:-translate-y-px hover:bg-hover/40 hover:shadow-pop"
                >
                  <Avatar name={c.name || '?'} size="lg" />
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{c.name || 'Без имени'}</span>
                    <span className="block truncate text-xs text-muted">{c.company || c.position || '—'}</span>
                  </span>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState icon="👋" title="Пока никого">
              Подключите Outlook или Google в «Синхронизации», загрузите файл или создайте контакт.
            </EmptyState>
          )}
        </section>
      </div>
    </Page>
  );
}

function BirthdayRow({ birthday }: { birthday: UpcomingBirthday }) {
  const when =
    birthday.days_until === 0
      ? 'сегодня'
      : birthday.days_until === 1
        ? 'завтра'
        : `через ${birthday.days_until} ${plural(birthday.days_until, 'день', 'дня', 'дней')}`;
  return (
    <li>
      <Link href={`/contacts/${birthday.contact_id}`} className="-mx-2 flex items-center gap-3 rounded px-2 py-1.5 hover:bg-hover">
        <span className="text-lg leading-none" aria-hidden>
          🎂
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm">{birthday.name}</span>
          <span className="block text-xs text-muted">
            {formatDate(birthday.date, false)}
            {birthday.turns ? ` · исполнится ${birthday.turns}` : ''}
          </span>
        </span>
        {birthday.days_until <= 1 ? <Tag color="pink">{when}</Tag> : <span className="shrink-0 text-xs text-faint">{when}</span>}
      </Link>
    </li>
  );
}

function ListSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2 py-1">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-8" />
      ))}
    </div>
  );
}
