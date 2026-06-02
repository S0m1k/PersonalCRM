'use client';

/**
 * Страница создания нового контакта.
 */

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import ContactForm from '../ContactForm';
import { isLoggedIn } from '../../../lib/api';

export default function NewContactPage() {
  const router = useRouter();

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push('/login');
    }
  }, [router]);

  return (
    <main style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: '1.25rem' }}>
        <Link href="/contacts" style={{ color: '#2563eb', textDecoration: 'none', fontSize: '0.9rem' }}>
          ← К списку контактов
        </Link>
      </div>
      <h1 style={{ marginBottom: '1.5rem' }}>Новый контакт</h1>
      <ContactForm />
    </main>
  );
}
