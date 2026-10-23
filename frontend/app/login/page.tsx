'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { login, saveToken } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const resp = await login(username, password);
      saveToken(resp.access_token);
      router.push('/');
    } catch {
      setError('Неверный логин или пароль');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center bg-sidebar px-4">
      <div className="w-full max-w-[340px] animate-fade-up">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-4 flex size-11 items-center justify-center rounded-lg bg-fg font-serif text-2xl font-bold italic text-bg">
            P
          </span>
          <h1 className="text-xl font-semibold tracking-tight">PersonalCRM</h1>
          <p className="mt-1 text-sm text-muted">Люди и всё, что о них важно помнить</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded-lg bg-surface p-5 shadow-pop">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted">Логин</span>
            <Input value={username} onChange={(e) => setUsername(e.target.value)} required autoComplete="username" />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted">Пароль</span>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoFocus
              autoComplete="current-password"
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" className="mt-1 w-full" disabled={isLoading}>
            {isLoading ? 'Вхожу…' : 'Войти'}
          </Button>
        </form>
      </div>
    </main>
  );
}
