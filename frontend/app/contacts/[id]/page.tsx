'use client';

/**
 * Страница просмотра и редактирования контакта (/contacts/[id]).
 *
 * При загрузке показывает данные контакта. Кнопка «Редактировать»
 * переключает в режим формы.
 */

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getContact, isLoggedIn, type Contact } from '../../../lib/api';
import ContactForm from '../ContactForm';

export default function ContactPage() {
  const router = useRouter();
  const params = useParams();
  const id = params?.id as string;

  const [contact, setContact] = useState<Contact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push('/login');
      return;
    }
    if (!id) return;

    getContact(id)
      .then((c) => setContact(c))
      .catch((err: unknown) => {
        if (err instanceof Error && err.message === 'Не авторизован') {
          router.push('/login');
          return;
        }
        setError('Контакт не найден или произошла ошибка');
      })
      .finally(() => setLoading(false));
  }, [id, router]);

  if (loading) {
    return <main><p>Загрузка…</p></main>;
  }

  if (error || !contact) {
    return (
      <main>
        <p style={{ color: '#c00' }}>{error ?? 'Контакт не найден'}</p>
        <Link href="/contacts">← К списку</Link>
      </main>
    );
  }

  const fullName = [contact.first_name, contact.last_name].filter(Boolean).join(' ') || '(без имени)';

  return (
    <main style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: '1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Link href="/contacts" style={{ color: '#2563eb', textDecoration: 'none', fontSize: '0.9rem' }}>
          ← К списку контактов
        </Link>
        {!editing && (
          <button onClick={() => setEditing(true)} style={editBtnStyle}>
            Редактировать
          </button>
        )}
      </div>

      {editing ? (
        <>
          <h1 style={{ marginBottom: '1.5rem' }}>Редактировать: {fullName}</h1>
          <ContactForm existing={contact} />
          <button onClick={() => setEditing(false)} style={{ marginTop: '0.5rem', color: '#888', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.9rem' }}>
            Отмена редактирования
          </button>
        </>
      ) : (
        <>
          <h1 style={{ marginBottom: '1.5rem' }}>{fullName}</h1>
          <ContactView contact={contact} />
        </>
      )}
    </main>
  );
}

// ---------------------------------------------------------------------------
// Компонент просмотра (не редактирования)
// ---------------------------------------------------------------------------

function ContactView({ contact }: { contact: Contact }) {
  return (
    <div style={{ background: '#fff', padding: '2rem', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.08)', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <Section title="Основное">
        <Row label="Имя" value={contact.first_name} />
        <Row label="Фамилия" value={contact.last_name} />
        <Row label="Компания" value={contact.company} />
        <Row label="Должность" value={contact.position} />
        <Row label="Город" value={contact.city} />
        <Row label="Дата рождения" value={contact.birthday ?? ''} />
        <Row label="Категория" value={contact.category} />
        <Row label="Приоритет" value={contact.priority} />
      </Section>

      {contact.phones.length > 0 && (
        <Section title="Телефоны">
          {contact.phones.map((p, i) => (
            <Row key={i} label={p.label} value={p.value} />
          ))}
        </Section>
      )}

      {contact.emails.length > 0 && (
        <Section title="Email">
          {contact.emails.map((e, i) => (
            <Row key={i} label={e.label} value={e.value} />
          ))}
        </Section>
      )}

      {contact.notes && (
        <Section title="Заметки">
          <p style={{ margin: 0, whiteSpace: 'pre-wrap', fontSize: '0.9rem' }}>{contact.notes}</p>
        </Section>
      )}

      {contact.custom_fields.length > 0 && (
        <Section title="Дополнительные поля">
          {contact.custom_fields.map((cf, i) => (
            <Row key={i} label={cf.key} value={cf.value} />
          ))}
        </Section>
      )}

      <p style={{ fontSize: '0.8rem', color: '#aaa', margin: 0 }}>
        Источник: {contact.source} · Создан: {new Date(contact.created_at).toLocaleDateString('ru')} · Обновлён: {new Date(contact.updated_at).toLocaleDateString('ru')}
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 style={{ margin: '0 0 0.5rem', fontSize: '0.9rem', color: '#666', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title}</h3>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div style={{ display: 'flex', gap: '1rem', fontSize: '0.9rem', marginBottom: '0.3rem' }}>
      <span style={{ color: '#888', minWidth: 120 }}>{label}</span>
      <span>{value}</span>
    </div>
  );
}

const editBtnStyle: React.CSSProperties = {
  padding: '0.4rem 1rem',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  cursor: 'pointer',
  fontWeight: 600,
};
