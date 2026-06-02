'use client';

/**
 * Страница входа.
 * После успешной аутентификации сохраняет токен в localStorage и редиректит на /contacts.
 */

import { useState, FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { login, saveToken } from '../../lib/api';

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const resp = await login(username, password);
      saveToken(resp.access_token);
      router.push('/contacts');
    } catch {
      setError('Неверный логин или пароль');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 360, margin: '4rem auto' }}>
      <h1 style={{ marginBottom: '1.5rem' }}>Войти в PersonalCRM</h1>

      <form
        onSubmit={handleSubmit}
        style={{
          background: '#fff',
          padding: '2rem',
          borderRadius: 8,
          boxShadow: '0 1px 4px rgba(0,0,0,0.1)',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
        }}
      >
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Логин</span>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoComplete="username"
            style={inputStyle}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Пароль</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
            style={inputStyle}
          />
        </label>

        {error && (
          <p style={{ color: '#c00', margin: 0, fontSize: '0.9rem' }}>{error}</p>
        )}

        <button
          type="submit"
          disabled={loading}
          style={btnStyle}
        >
          {loading ? 'Вход…' : 'Войти'}
        </button>
      </form>
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '0.5rem 0.75rem',
  border: '1px solid #ccc',
  borderRadius: 4,
  fontSize: '1rem',
  outline: 'none',
};

const btnStyle: React.CSSProperties = {
  padding: '0.6rem',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  fontSize: '1rem',
  cursor: 'pointer',
  fontWeight: 600,
};
