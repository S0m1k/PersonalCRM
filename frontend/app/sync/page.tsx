'use client';

/**
 * Страница синхронизации (/sync).
 *
 * - Список подключённых провайдеров (sync_connections)
 * - Кнопка «Подключить Outlook» (редирект на authorize_url; если Azure не
 *   настроен — показываем понятное сообщение)
 * - Кнопка «Синхронизировать» на каждом подключении
 * - История синхронизаций (sync_log)
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  connectGoogle,
  connectMicrosoft,
  deleteConnection,
  getConnections,
  getSyncLog,
  isLoggedIn,
  triggerSync,
  type SyncConnection,
  type SyncLogEntry,
} from '../../lib/api';

export default function SyncPage() {
  const router = useRouter();
  const [connections, setConnections] = useState<SyncConnection[]>([]);
  const [log, setLog] = useState<SyncLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handle401 = useCallback(() => router.push('/login'), [router]);

  const load = useCallback(async () => {
    try {
      const [conns, logs] = await Promise.all([getConnections(), getSyncLog()]);
      setConnections(conns);
      setLog(logs);
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') return handle401();
      setMessage('Не удалось загрузить данные синхронизации.');
    } finally {
      setLoading(false);
    }
  }, [handle401]);

  useEffect(() => {
    if (!isLoggedIn()) return handle401();
    void load();

    // Показать сообщение после OAuth-редиректа (?connected / ?error)
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected')) setMessage('✓ Провайдер подключён.');
    if (params.get('error')) setMessage(`Ошибка подключения: ${params.get('error')}`);
  }, [handle401, load]);

  async function handleConnect(provider: 'microsoft' | 'google') {
    setBusy(true);
    setMessage(null);
    try {
      const { authorize_url } =
        provider === 'microsoft' ? await connectMicrosoft() : await connectGoogle();
      window.location.href = authorize_url;
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') return handle401();
      const text = err instanceof Error ? err.message : '';
      if (text.includes('Azure') || text.includes('Google') || text.includes('501')) {
        setMessage(
          provider === 'microsoft'
            ? 'Outlook OAuth ещё не настроен: задай MS_CLIENT_ID / MS_CLIENT_SECRET / MS_REDIRECT_URI в backend/.env (регистрация в Azure AD).'
            : 'Google OAuth ещё не настроен: задай GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI в backend/.env (Google Cloud Console).',
        );
      } else {
        setMessage('Не удалось начать подключение.');
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleSync(id: string) {
    setBusy(true);
    setMessage(null);
    try {
      const result = await triggerSync(id);
      const s = result.stats;
      setMessage(
        `Синхронизация завершена: создано ${s.created}, слито ${s.merged}, ошибок ${s.errors}.`,
      );
      await load();
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') return handle401();
      setMessage('Ошибка синхронизации.');
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Отключить провайдера? Токены будут удалены.')) return;
    try {
      await deleteConnection(id);
      await load();
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') return handle401();
      setMessage('Не удалось отключить.');
    }
  }

  return (
    <main style={{ maxWidth: 760 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <h1 style={{ margin: 0 }}>Синхронизация</h1>
        <nav style={{ display: 'flex', gap: '1rem', fontSize: '0.9rem' }}>
          <Link href="/contacts" style={linkStyle}>Контакты</Link>
          <Link href="/import" style={linkStyle}>Импорт файла</Link>
        </nav>
      </div>

      {message && (
        <div style={msgStyle}>{message}</div>
      )}

      <section style={cardStyle}>
        <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>Подключения</h2>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button onClick={() => handleConnect('microsoft')} disabled={busy} style={primaryBtn}>
            + Подключить Outlook
          </button>
          <button onClick={() => handleConnect('google')} disabled={busy} style={{ ...primaryBtn, background: '#dc2626' }}>
            + Подключить Google
          </button>
        </div>

        {loading ? (
          <p>Загрузка…</p>
        ) : connections.length === 0 ? (
          <p style={{ color: '#888', fontSize: '0.9rem' }}>Пока нет подключённых провайдеров.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '1rem' }}>
            <tbody>
              {connections.map((c) => (
                <tr key={c.id} style={{ borderTop: '1px solid #eee' }}>
                  <td style={{ padding: '0.6rem 0', fontWeight: 600, textTransform: 'capitalize' }}>{c.provider}</td>
                  <td style={{ padding: '0.6rem 0', fontSize: '0.85rem', color: '#888' }}>
                    {c.contacts_last_sync
                      ? `синк: ${new Date(c.contacts_last_sync).toLocaleString('ru')}`
                      : 'ещё не синхронизировано'}
                  </td>
                  <td style={{ padding: '0.6rem 0', textAlign: 'right' }}>
                    <button onClick={() => handleSync(c.id)} disabled={busy} style={smallBtn}>Синхронизировать</button>
                    <button onClick={() => handleDelete(c.id)} style={{ ...smallBtn, color: '#b91c1c', marginLeft: 8 }}>Отключить</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section style={cardStyle}>
        <h2 style={{ marginTop: 0, fontSize: '1.1rem' }}>История</h2>
        {log.length === 0 ? (
          <p style={{ color: '#888', fontSize: '0.9rem' }}>История пуста.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ color: '#888', textAlign: 'left' }}>
                <th style={{ padding: '0.3rem 0' }}>Действие</th>
                <th>Создано</th>
                <th>Слито</th>
                <th>Пропущено</th>
                <th>Ошибки</th>
                <th>Когда</th>
              </tr>
            </thead>
            <tbody>
              {log.map((l) => (
                <tr key={l.id} style={{ borderTop: '1px solid #eee' }}>
                  <td style={{ padding: '0.4rem 0' }}>{l.action}</td>
                  <td>{l.stats.created}</td>
                  <td>{l.stats.merged}</td>
                  <td>{l.stats.skipped}</td>
                  <td style={{ color: l.stats.errors ? '#b91c1c' : 'inherit' }}>{l.stats.errors}</td>
                  <td style={{ color: '#888' }}>{new Date(l.started_at).toLocaleString('ru')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

const linkStyle: React.CSSProperties = { color: '#2563eb', textDecoration: 'none' };
const cardStyle: React.CSSProperties = {
  background: '#fff',
  padding: '1.5rem',
  borderRadius: 8,
  boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
  marginBottom: '1.25rem',
};
const msgStyle: React.CSSProperties = {
  background: '#eff6ff',
  border: '1px solid #bfdbfe',
  color: '#1e40af',
  padding: '0.75rem 1rem',
  borderRadius: 6,
  marginBottom: '1.25rem',
  fontSize: '0.9rem',
};
const primaryBtn: React.CSSProperties = {
  padding: '0.5rem 1.2rem',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  fontWeight: 600,
  cursor: 'pointer',
};
const smallBtn: React.CSSProperties = {
  padding: '0.35rem 0.8rem',
  background: 'transparent',
  border: '1px solid #ccc',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: '0.85rem',
};
