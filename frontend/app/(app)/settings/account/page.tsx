'use client';

/**
 * Аккаунт (/settings/account): кто вошёл, смена пароля, доступ телефона.
 */

import { useState, type FormEvent } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { Monitor, Moon, Sun, UserRound, type LucideIcon } from 'lucide-react';
import { changePassword, meKey, type Me } from '@/lib/api';
import { cn, errorText } from '@/lib/utils';
import { Page, PageHeader, SectionTitle, Skeleton } from '@/components/app/page';
import { PhoneSyncCard } from '@/components/app/phone-sync-card';
import { ACCENTS, useAppearance, type ThemeMode } from '@/components/app/theme';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

// Совпадает с backend/app/models/user.py
const PASSWORD_MIN = 8;

export default function AccountPage() {
  const { data: me } = useSWR<Me>(meKey);

  return (
    <Page>
      <PageHeader icon={UserRound} title="Аккаунт" description="Ваши контакты видите только вы: у каждого аккаунта своя база." />

      <section className="mb-10">
        <SectionTitle>Профиль</SectionTitle>
        {me ? (
          <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 pt-2 text-sm">
            <dt className="text-muted">Email</dt>
            <dd>{me.email}</dd>
            <dt className="text-muted">Имя</dt>
            <dd>{me.name || <span className="text-faint">не указано</span>}</dd>
          </dl>
        ) : (
          <Skeleton className="mt-2 h-10 w-64" />
        )}
      </section>

      <section className="mb-10">
        <SectionTitle>Оформление</SectionTitle>
        <AppearanceSettings />
      </section>

      <section className="mb-10">
        <SectionTitle>Пароль</SectionTitle>
        <PasswordForm />
      </section>

      <section>
        <SectionTitle>Телефон</SectionTitle>
        <div className="pt-3">
          <PhoneSyncCard />
        </div>
      </section>
    </Page>
  );
}

const THEME_OPTIONS: { value: ThemeMode; label: string; icon: LucideIcon }[] = [
  { value: 'light', label: 'Светлая', icon: Sun },
  { value: 'dark', label: 'Тёмная', icon: Moon },
  { value: 'system', label: 'Как в системе', icon: Monitor },
];

function AppearanceSettings() {
  const { mode, setMode, accent, setAccent } = useAppearance();

  return (
    <div className="flex flex-col gap-5 pt-3">
      <div role="radiogroup" aria-label="Тема" className="flex flex-wrap gap-2">
        {THEME_OPTIONS.map(({ value, label, icon: Icon }) => (
          <Button
            key={value}
            role="radio"
            aria-checked={mode === value}
            variant={mode === value ? 'primary' : 'outline'}
            onClick={() => setMode(value)}
          >
            <Icon />
            {label}
          </Button>
        ))}
      </div>

      <div>
        <div className="mb-2 text-xs font-medium text-muted">Цвет акцента</div>
        <div role="radiogroup" aria-label="Цвет акцента" className="flex flex-wrap gap-2">
          {ACCENTS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={accent === id}
              onClick={() => setAccent(id)}
              className={cn(
                'flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors',
                accent === id ? 'border-accent bg-hover text-fg' : 'border-line bg-surface text-muted hover:bg-hover hover:text-fg',
              )}
            >
              {/* Образец цвета пресета: свой класс .accent-<id> переопределяет шкалу только внутри точки */}
              <span aria-hidden className={cn('size-4 rounded-full bg-accent-500', `accent-${id}`)} />
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function PasswordForm() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setIsSaving(true);
    try {
      await changePassword(current, next);
      setCurrent('');
      setNext('');
      toast.success('Пароль изменён, на других устройствах нужно войти заново');
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex max-w-sm flex-col gap-3 pt-3">
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted">Текущий пароль</span>
        <Input
          type="password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          required
          autoComplete="current-password"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium text-muted">Новый пароль</span>
        <Input
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          required
          minLength={PASSWORD_MIN}
          maxLength={128}
          autoComplete="new-password"
        />
        <span className="text-xs text-faint">Не короче {PASSWORD_MIN} символов</span>
      </label>
      <Button type="submit" className="self-start" disabled={isSaving}>
        {isSaving ? 'Сохраняю…' : 'Сменить пароль'}
      </Button>
    </form>
  );
}
