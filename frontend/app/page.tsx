/**
 * Главная страница — статус health-check + навигация.
 *
 * Запрос к API делается на сервере (Server Component) чтобы избежать CORS при SSR.
 */

import Link from 'next/link';

interface HealthResponse {
  status: string;
  db: string;
  db_error?: string;
}

async function fetchHealth(): Promise<HealthResponse | null> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  try {
    const res = await fetch(`${apiUrl}/api/health`, {
      cache: 'no-store',
    });

    if (!res.ok) return null;
    return res.json() as Promise<HealthResponse>;
  } catch {
    return null;
  }
}

export default async function HomePage() {
  const health = await fetchHealth();

  const apiOk = health?.status === 'ok';
  const dbOk = health?.db === 'ok';

  return (
    <main>
      <h1>PersonalCRM</h1>
      <p>Персональная CRM с синхронизацией контактов из Outlook, Google и ручным импортом.</p>

      {/* Навигация */}
      <nav style={{ display: 'flex', gap: '1rem', margin: '1.5rem 0' }}>
        <Link
          href="/contacts"
          style={{
            padding: '0.5rem 1.25rem',
            background: '#2563eb',
            color: '#fff',
            borderRadius: 6,
            textDecoration: 'none',
            fontWeight: 600,
          }}
        >
          Контакты
        </Link>
        <Link
          href="/login"
          style={{
            padding: '0.5rem 1.25rem',
            background: '#fff',
            color: '#2563eb',
            border: '1px solid #2563eb',
            borderRadius: 6,
            textDecoration: 'none',
            fontWeight: 600,
          }}
        >
          Войти
        </Link>
      </nav>

      <section
        style={{
          marginTop: '1.5rem',
          padding: '1.5rem',
          background: '#fff',
          borderRadius: '8px',
          boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
          maxWidth: '480px',
        }}
      >
        <h2 style={{ marginTop: 0 }}>Статус сервисов</h2>

        {health === null ? (
          <p style={{ color: '#c00' }}>
            Бэкенд недоступен. Убедитесь, что запущен{' '}
            <code>docker-compose up</code> или <code>uvicorn</code>.
          </p>
        ) : (
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <tbody>
              <StatusRow label="API" ok={apiOk} />
              <StatusRow label="MongoDB" ok={dbOk} detail={health.db_error} />
            </tbody>
          </table>
        )}
      </section>

      <p style={{ marginTop: '2rem', fontSize: '0.9rem', color: '#666' }}>
        Sprint 1 — ядро CRM: контакты, авторизация, CRUD.
      </p>
    </main>
  );
}

function StatusRow({
  label,
  ok,
  detail,
}: {
  label: string;
  ok: boolean;
  detail?: string;
}) {
  return (
    <tr>
      <td style={{ padding: '0.4rem 0.8rem 0.4rem 0', fontWeight: 600 }}>{label}</td>
      <td style={{ padding: '0.4rem 0', color: ok ? '#0a0' : '#c00' }}>
        {ok ? '✓ OK' : '✗ Ошибка'}
      </td>
      {detail && (
        <td style={{ padding: '0.4rem 0 0.4rem 0.8rem', fontSize: '0.85rem', color: '#888' }}>
          {detail}
        </td>
      )}
    </tr>
  );
}
