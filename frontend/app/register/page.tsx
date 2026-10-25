'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { register, saveToken } from '@/lib/api';
import { errorText } from '@/lib/utils';
import { AuthCard, AuthError, AuthField } from '@/components/app/auth-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

// Совпадает с backend/app/models/user.py
const PASSWORD_MIN = 8;

export default function RegisterPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const resp = await register(email, password, name);
      saveToken(resp.access_token);
      router.push('/');
    } catch (err) {
      setError(errorText(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <AuthCard
      subtitle="Новый аккаунт — у каждого своя база контактов"
      onSubmit={handleSubmit}
      footer={
        <>
          Уже есть аккаунт?{' '}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Войти
          </Link>
        </>
      }
    >
      <AuthField label="Как вас зовут">
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} autoFocus autoComplete="name" />
      </AuthField>
      <AuthField label="Email">
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          maxLength={254}
          autoComplete="email"
        />
      </AuthField>
      <AuthField label="Пароль" hint={`Не короче ${PASSWORD_MIN} символов`}>
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={PASSWORD_MIN}
          maxLength={128}
          autoComplete="new-password"
        />
      </AuthField>
      <AuthError message={error} />
      <Button type="submit" variant="primary" className="mt-1 w-full" disabled={isLoading}>
        {isLoading ? 'Создаю…' : 'Создать аккаунт'}
      </Button>
    </AuthCard>
  );
}
