'use client';

/**
 * Страница списка контактов.
 * Показывает строку поиска, фильтры по категории/приоритету, таблицу контактов.
 */

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  getContacts,
  deleteContact,
  clearToken,
  isLoggedIn,
  type Contact,
} from '../../lib/api';

export default function ContactsPage() {
  const router = useRouter();

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Фильтры
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [priority, setPriority] = useState('');

  const fetchContacts = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getContacts({ q: q || undefined, category: category || undefined, priority: priority || undefined });
      setContacts(data);
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') {
        router.push('/login');
        return;
      }
      setError('Ошибка загрузки контактов');
    } finally {
      setLoading(false);
    }
  }, [q, category, priority, router]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push('/login');
      return;
    }
    fetchContacts();
  }, [fetchContacts, router]);

  async function handleDelete(id: string, name: string) {
    if (!confirm(`Удалить контакт «${name}»?`)) return;
    try {
      await deleteContact(id);
      setContacts((prev) => prev.filter((c) => c.id !== id));
    } catch {
      alert('Ошибка при удалении');
    }
  }

  function handleLogout() {
    clearToken();
    router.push('/login');
  }

  return (
    <main>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <h1 style={{ margin: 0 }}>Контакты</h1>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Link href="/contacts/new" style={linkBtnStyle}>
            + Добавить
          </Link>
          <button onClick={handleLogout} style={outlineBtnStyle}>
            Выйти
          </button>
        </div>
      </div>

      {/* Поиск и фильтры */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <input
          type="search"
          placeholder="Поиск по имени, компании, email, телефону…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ ...inputStyle, flex: '1 1 240px' }}
        />
        <input
          type="text"
          placeholder="Категория"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={{ ...inputStyle, width: 140 }}
        />
        <input
          type="text"
          placeholder="Приоритет"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
          style={{ ...inputStyle, width: 120 }}
        />
        <button onClick={fetchContacts} style={btnStyle}>
          Найти
        </button>
      </div>

      {/* Результаты */}
      {loading && <p>Загрузка…</p>}
      {error && <p style={{ color: '#c00' }}>{error}</p>}

      {!loading && !error && contacts.length === 0 && (
        <p style={{ color: '#888' }}>Контактов не найдено. <Link href="/contacts/new">Добавить первый?</Link></p>
      )}

      {!loading && contacts.length > 0 && (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
            <thead>
              <tr style={{ background: '#f0f4ff', textAlign: 'left' }}>
                {['Имя', 'Компания', 'Телефон', 'Email', 'Категория', 'Приоритет', 'Действия'].map((h) => (
                  <th key={h} style={{ padding: '0.6rem 0.8rem', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid #dde' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {contacts.map((c) => {
                const fullName = [c.first_name, c.last_name].filter(Boolean).join(' ') || '(без имени)';
                const phone = c.phones[0]?.value ?? '—';
                const email = c.emails[0]?.value ?? '—';
                return (
                  <tr key={c.id} style={{ borderBottom: '1px solid #eee' }}>
                    <td style={tdStyle}>
                      <Link href={`/contacts/${c.id}`} style={{ color: '#2563eb', textDecoration: 'none', fontWeight: 500 }}>
                        {fullName}
                      </Link>
                    </td>
                    <td style={tdStyle}>{c.company || '—'}</td>
                    <td style={tdStyle}>{phone}</td>
                    <td style={tdStyle}>{email}</td>
                    <td style={tdStyle}>{c.category || '—'}</td>
                    <td style={tdStyle}>{c.priority || '—'}</td>
                    <td style={tdStyle}>
                      <div style={{ display: 'flex', gap: '0.4rem' }}>
                        <Link href={`/contacts/${c.id}`} style={smallLinkStyle}>
                          Редактировать
                        </Link>
                        <button
                          onClick={() => handleDelete(c.id, fullName)}
                          style={smallDangerBtn}
                        >
                          Удалить
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <p style={{ marginTop: '1rem', fontSize: '0.85rem', color: '#888' }}>
        Найдено: {contacts.length}
      </p>
    </main>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '0.45rem 0.7rem',
  border: '1px solid #ccc',
  borderRadius: 4,
  fontSize: '0.95rem',
};

const btnStyle: React.CSSProperties = {
  padding: '0.45rem 1rem',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  cursor: 'pointer',
  fontWeight: 600,
};

const outlineBtnStyle: React.CSSProperties = {
  padding: '0.45rem 1rem',
  background: 'transparent',
  color: '#555',
  border: '1px solid #ccc',
  borderRadius: 4,
  cursor: 'pointer',
};

const linkBtnStyle: React.CSSProperties = {
  padding: '0.45rem 1rem',
  background: '#16a34a',
  color: '#fff',
  borderRadius: 4,
  textDecoration: 'none',
  fontWeight: 600,
};

const tdStyle: React.CSSProperties = {
  padding: '0.55rem 0.8rem',
  fontSize: '0.9rem',
  verticalAlign: 'middle',
};

const smallLinkStyle: React.CSSProperties = {
  padding: '0.25rem 0.5rem',
  background: '#e0e7ff',
  color: '#3730a3',
  borderRadius: 3,
  textDecoration: 'none',
  fontSize: '0.8rem',
};

const smallDangerBtn: React.CSSProperties = {
  padding: '0.25rem 0.5rem',
  background: '#fee2e2',
  color: '#b91c1c',
  border: 'none',
  borderRadius: 3,
  cursor: 'pointer',
  fontSize: '0.8rem',
};
