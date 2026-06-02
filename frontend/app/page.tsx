/**
 * Главная страница — отображает статус health-check бэкенда.
 *
 * Запрос к API делается на сервере (Server Component), чтобы избежать CORS
 * при SSR. Для клиентских обновлений в реальном приложении используйте
 * React Query / SWR (добавим в Sprint 1).
 */

interface HealthResponse {
  status: string;
  db: string;
  db_error?: string;
}

async function fetchHealth(): Promise<HealthResponse | null> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

  try {
    const res = await fetch(`${apiUrl}/api/health`, {
      // next: { revalidate: 30 } — обновлять каждые 30 с (раскомментируйте при необходимости)
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

      <section
        style={{
          marginTop: '2rem',
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
            ❌ Бэкенд недоступен. Убедитесь, что запущен{' '}
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
        Sprint 0 — скелет проекта. Следующий шаг: Sprint 1 — модель контакта и CRUD.
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
