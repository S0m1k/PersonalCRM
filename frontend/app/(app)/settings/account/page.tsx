'use client';

/**
 * Аккаунт (/settings/account): кто вошёл, смена пароля, доступ телефона.
 */

import { useState, type FormEvent } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { UserRound } from 'lucide-react';
import { changePassword, meKey, type Me } from '@/lib/api';
import { errorText } from '@/lib/utils';
import { Page, PageHeader, SectionTitle, Skeleton } from '@/components/app/page';
import { PhoneSyncCard } from '@/components/app/phone-sync-card';
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
