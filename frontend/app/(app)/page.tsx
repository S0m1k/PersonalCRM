'use client';

import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { Cake, Plus } from 'lucide-react';
import { homeKey, meKey, type HomeSummary, type Me, type UpcomingBirthday } from '@/lib/api';
import { markTouched, snoozeContact, type HomeInteraction, type KeepInTouchItem } from '@/lib/api-crm';
import { completeReminder, type Reminder } from '@/lib/api-reminders';
import { errorText, formatDate, plural, relativeTime } from '@/lib/utils';
import { useAppActions } from '@/components/app/app-shell';
import { Skeleton } from '@/components/app/page';
import { TodayEvents } from '@/components/calendar/event-blocks';
import { AiPrompt } from '@/components/home/ai-prompt';
import { HomeSidePanel } from '@/components/home/onboarding-card';
import { HomeSection } from '@/components/home/section';
import { ReminderRow } from '@/components/reminders/reminder-row';
import { Avatar } from '@/components/app/avatar';
import { Button } from '@/components/ui/button';

const SNOOZE_DAYS = 7;
const NIGHT_END = 5;
const MORNING_END = 12;
const DAY_END = 18;

function greeting(hour: number = new Date().getHours()): string {
  if (hour < NIGHT_END) return 'Доброй ночи';
  if (hour < MORNING_END) return 'Доброе утро';
  if (hour < DAY_END) return 'Добрый день';
  return 'Добрый вечер';
}

function displayName(me: Me | undefined): string {
  if (!me) return '';
  return me.name?.trim().split(/\s+/)[0] || me.email.split('@')[0];
}

export default function HomePage() {
  const { newContact } = useAppActions();
  const { mutate: mutateGlobal } = useSWRConfig();
  const { data: me } = useSWR<Me>(meKey);
  const { data: home, isLoading, mutate } = useSWR<HomeSummary>(homeKey());

  async function run(action: () => Promise<unknown>) {
    try {
      await action();
      await Promise.all([mutate(), mutateGlobal((key) => typeof key === 'string' && key.startsWith('/api/keep-in-touch'))]);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  const name = displayName(me);

  return (
    <div className="mx-auto flex w-full max-w-[1200px] gap-10 px-4 pb-24 pt-8 sm:px-12 sm:pt-14 lg:px-16">
      <div className="min-w-0 max-w-[720px] flex-1">
        <header className="mb-6 flex animate-fade-up items-start justify-between gap-3">
          <h1 className="font-display text-[32px] font-semibold leading-tight tracking-[-0.01em]">
            {greeting()}
            {name && `, ${name}`}
          </h1>
          <Button variant="outline" size="sm" onClick={() => newContact()}>
            <Plus /> Новый контакт
          </Button>
        </header>

        <div className="mb-10">
          <AiPrompt />
        </div>

        <div className="flex flex-col gap-8">
          <HomeSection title="Календарь" href="/calendar" linkLabel="Все →">
            <TodayEvents />
          </HomeSection>

          <HomeSection title="Дни рождения" href="/contacts/birthdays" linkLabel="Все дни рождения →">
            {isLoading ? (
              <ListSkeleton rows={2} />
            ) : home?.birthdays.length ? (
              <ul>
                {home.birthdays.map((b) => (
                  <BirthdayRow key={b.contact_id} birthday={b} />
                ))}
              </ul>
            ) : (
              <Empty>В ближайшие две недели дней рождения нет.</Empty>
            )}
          </HomeSection>

          <HomeSection title="Keep in touch" href="/keep-in-touch" linkLabel="Все →">
            {isLoading ? (
              <ListSkeleton />
            ) : home?.keep_in_touch_overdue.length ? (
              <ul>
                {home.keep_in_touch_overdue.map((item) => (
                  <KeepInTouchRow
                    key={item.contact_id}
                    item={item}
                    onTouched={() => run(() => markTouched(item.contact_id))}
                    onSnooze={() => run(() => snoozeContact(item.contact_id, SNOOZE_DAYS))}
                  />
                ))}
              </ul>
            ) : (
              <Empty>Всем, с кем вы хотели поддерживать связь, уже написано.</Empty>
            )}
          </HomeSection>

          <HomeSection title="Напоминания" href="/reminders" linkLabel="Все →">
            {isLoading ? (
              <ListSkeleton />
            ) : home?.reminders.length ? (
              <ul>
                {home.reminders.map((r: Reminder) => (
                  <ReminderRow key={r.id} reminder={r} onToggle={(x) => run(() => completeReminder(x.id))} />
                ))}
              </ul>
            ) : (
              <Empty>Напоминаний нет.</Empty>
            )}
          </HomeSection>

          <HomeSection title="Последние взаимодействия" href="/timeline" linkLabel="Все →">
            {isLoading ? (
              <ListSkeleton />
            ) : home?.recent_interactions.length ? (
              <ul>
                {home.recent_interactions.map((i) => (
                  <InteractionRow key={i.id} interaction={i} />
                ))}
              </ul>
            ) : (
              <Empty>Пока ни одного взаимодействия.</Empty>
            )}
          </HomeSection>
        </div>
      </div>

      <HomeSidePanel home={home} />
    </div>
  );
}

function Empty({ children }: { children: string }) {
  return <p className="py-1 text-sm text-faint">{children}</p>;
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

function BirthdayRow({ birthday }: { birthday: UpcomingBirthday }) {
  const when =
    birthday.days_until === 0
      ? 'сегодня'
      : birthday.days_until === 1
        ? 'завтра'
        : `через ${birthday.days_until} ${plural(birthday.days_until, 'день', 'дня', 'дней')}`;
  return (
    <li>
      <Link href={`/contacts/${birthday.contact_id}`} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-hover">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-crm-birthday/20 text-crm-birthday" aria-hidden>
          <Cake className="size-3.5" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm">{birthday.name}</span>
          <span className="block text-xs text-muted">
            {formatDate(birthday.date, false)}
            {birthday.turns ? ` · исполнится ${birthday.turns}` : ''}
          </span>
        </span>
        <span className="shrink-0 text-xs text-muted">{when}</span>
      </Link>
    </li>
  );
}

function KeepInTouchRow({ item, onTouched, onSnooze }: { item: KeepInTouchItem; onTouched: () => void; onSnooze: () => void }) {
  return (
    <li className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-hover/60">
      <Link href={`/contacts/${item.contact_id}`} className="flex min-w-0 flex-1 items-center gap-3">
        <Avatar name={item.name || '?'} />
        <span className="min-w-0">
          <span className="block truncate text-sm">{item.name || 'Без имени'}</span>
          <span className="block text-xs text-danger">
            просрочено на {item.days_overdue} {plural(item.days_overdue, 'день', 'дня', 'дней')}
          </span>
        </span>
      </Link>
      <Button variant="outline" size="sm" onClick={onTouched}>
        Связался
      </Button>
      <Button variant="ghost" size="sm" onClick={onSnooze} title={`Отложить на ${SNOOZE_DAYS} дней`}>
        Отложить
      </Button>
    </li>
  );
}

const KIND_LABELS: Record<HomeInteraction['kind'], string> = {
  note: 'Заметка',
  call: 'Звонок',
  meeting: 'Встреча',
  message: 'Сообщение',
  email: 'Письмо',
  other: 'Другое',
};

function InteractionRow({ interaction }: { interaction: HomeInteraction }) {
  const people = interaction.contacts.map((c) => c.name).join(', ');
  const first = interaction.contacts[0];
  const content = (
    <>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm">{interaction.title || KIND_LABELS[interaction.kind]}</span>
        <span className="block truncate text-xs text-muted">
          {KIND_LABELS[interaction.kind]}
          {people && ` · ${people}`}
        </span>
      </span>
      <span className="shrink-0 text-xs text-faint">{relativeTime(interaction.occurred_at)}</span>
    </>
  );
  return (
    <li>
      {first ? (
        <Link href={`/contacts/${first.id}`} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-hover">
          {content}
        </Link>
      ) : (
        <div className="-mx-2 flex items-center gap-3 px-2 py-1.5">{content}</div>
      )}
    </li>
  );
}
