'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { login, saveToken } from '@/lib/api';
import { errorText } from '@/lib/utils';
import { AuthCard, AuthError, AuthField } from '@/components/app/auth-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const resp = await login(email, password);
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
      subtitle="Люди и всё, что о них важно помнить"
      onSubmit={handleSubmit}
      footer={
        <>
          Нет аккаунта?{' '}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Зарегистрироваться
          </Link>
        </>
      }
    >
      <AuthField label="Email">
        <Input
          type="text"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          autoFocus
          autoComplete="username"
        />
      </AuthField>
      <AuthField label="Пароль">
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          autoComplete="current-password"
        />
      </AuthField>
      <AuthError message={error} />
      <Button type="submit" variant="primary" className="mt-1 w-full" disabled={isLoading}>
        {isLoading ? 'Вхожу…' : 'Войти'}
      </Button>
    </AuthCard>
  );
}
