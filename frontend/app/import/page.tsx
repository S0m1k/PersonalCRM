'use client';

/**
 * Страница импорта контактов из файла (/import).
 *
 * Поток: выбрать файл → загрузить → превью с классификацией дублей →
 * подтвердить. Для неоднозначных совпадений (suggest_merge) пользователь
 * выбирает: слить / создать новый / пропустить.
 */

import { useCallback, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  confirmImport,
  getImportPreview,
  uploadImportFile,
  type ImportDecision,
  type ImportPreview,
  type PreviewItem,
} from '../../lib/api';

type SuggestChoice = 'merge' | 'create' | 'skip';

export default function ImportPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [choices, setChoices] = useState<Record<number, SuggestChoice>>({});
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const handle401 = useCallback(() => router.push('/login'), [router]);

  async function handleUpload() {
    if (!file) return;
    setBusy(true);
    setMessage(null);
    try {
      const up = await uploadImportFile(file);
      const prev = await getImportPreview(up.import_id);
      setPreview(prev);
      // По умолчанию неоднозначные дубли — пропускаем
      const init: Record<number, SuggestChoice> = {};
      prev.items.forEach((it) => {
        if (it.classification === 'suggest_merge') init[it.index] = 'skip';
      });
      setChoices(init);
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') return handle401();
      setMessage(`Ошибка загрузки: ${err instanceof Error ? err.message : 'неизвестно'}`);
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!preview) return;
    setBusy(true);
    setMessage(null);
    try {
      // Решения только для suggest_merge; auto_merge/new используют дефолты сервера
      const decisions: ImportDecision[] = preview.items
        .filter((it) => it.classification === 'suggest_merge')
        .map((it) => {
          const choice = choices[it.index] ?? 'skip';
          if (choice === 'merge') {
            return { index: it.index, action: 'merge', existing_id: it.best_match?.existing_id };
          }
          if (choice === 'create') return { index: it.index, action: 'create' };
          return { index: it.index, action: 'skip' };
        });

      const result = await confirmImport(preview.import_id, decisions);
      setDone(`Импорт завершён: создано ${result.created}, слито ${result.merged}, пропущено ${result.skipped}.`);
      setPreview(null);
      setFile(null);
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') return handle401();
      setMessage('Ошибка при подтверждении импорта.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 820 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
        <h1 style={{ margin: 0 }}>Импорт контактов</h1>
        <nav style={{ display: 'flex', gap: '1rem', fontSize: '0.9rem' }}>
          <Link href="/contacts" style={linkStyle}>Контакты</Link>
          <Link href="/sync" style={linkStyle}>Синхронизация</Link>
        </nav>
      </div>

      {done && <div style={{ ...msgStyle, background: '#ecfdf5', borderColor: '#a7f3d0', color: '#065f46' }}>{done}</div>}
      {message && <div style={{ ...msgStyle, background: '#fef2f2', borderColor: '#fecaca', color: '#991b1b' }}>{message}</div>}

      {!preview && (
        <section style={cardStyle}>
          <p style={{ marginTop: 0, fontSize: '0.9rem', color: '#555' }}>
            Поддерживаются файлы <b>.csv</b> (экспорт Google Contacts), <b>.vcf</b> (vCard) и{' '}
            <b>.json</b> (экспорт Telegram).
          </p>
          <input
            type="file"
            accept=".csv,.vcf,.json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            style={{ display: 'block', marginBottom: '1rem' }}
          />
          <button onClick={handleUpload} disabled={!file || busy} style={primaryBtn}>
            {busy ? 'Загрузка…' : 'Загрузить и проверить'}
          </button>
        </section>
      )}

      {preview && (
        <section style={cardStyle}>
          <p style={{ marginTop: 0 }}>
            Найдено <b>{preview.total}</b> контактов: новых <b>{preview.new_count}</b>,
            автоматическое слияние <b>{preview.auto_merge_count}</b>,
            требуют решения <b>{preview.suggest_count}</b>.
          </p>

          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ color: '#888', textAlign: 'left' }}>
                <th style={{ padding: '0.3rem 0' }}>Контакт</th>
                <th>Статус</th>
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {preview.items.map((it) => (
                <ImportRow
                  key={it.index}
                  item={it}
                  choice={choices[it.index] ?? 'skip'}
                  onChoice={(c) => setChoices((prev) => ({ ...prev, [it.index]: c }))}
                />
              ))}
            </tbody>
          </table>

          <div style={{ marginTop: '1.5rem', display: 'flex', gap: '0.75rem' }}>
            <button onClick={handleConfirm} disabled={busy} style={primaryBtn}>
              {busy ? 'Применение…' : 'Подтвердить импорт'}
            </button>
            <button onClick={() => { setPreview(null); setFile(null); }} style={cancelBtn}>
              Отмена
            </button>
          </div>
        </section>
      )}
    </main>
  );
}

function ImportRow({
  item,
  choice,
  onChoice,
}: {
  item: PreviewItem;
  choice: SuggestChoice;
  onChoice: (c: SuggestChoice) => void;
}) {
  const name =
    [item.contact.first_name, item.contact.last_name].filter(Boolean).join(' ') || '(без имени)';

  return (
    <tr style={{ borderTop: '1px solid #eee', verticalAlign: 'top' }}>
      <td style={{ padding: '0.5rem 0' }}>
        <div style={{ fontWeight: 600 }}>{name}</div>
        <div style={{ color: '#888' }}>
          {item.contact.phones?.map((p) => p.value).join(', ')}
          {item.contact.emails?.length ? ` · ${item.contact.emails.map((e) => e.value).join(', ')}` : ''}
        </div>
      </td>
      <td style={{ padding: '0.5rem 0' }}>
        {item.classification === 'new' && <span style={{ color: '#059669' }}>Новый</span>}
        {item.classification === 'auto_merge' && (
          <span style={{ color: '#2563eb' }}>
            Авто-слияние{item.best_match ? ` → ${item.best_match.name}` : ''}
          </span>
        )}
        {item.classification === 'suggest_merge' && item.best_match && (
          <span style={{ color: '#b45309' }}>
            Похож на {item.best_match.name} ({item.best_match.score}%)
            <br />
            <span style={{ color: '#aaa', fontSize: '0.8rem' }}>{item.best_match.reasons.join(', ')}</span>
          </span>
        )}
      </td>
      <td style={{ padding: '0.5rem 0' }}>
        {item.classification === 'suggest_merge' ? (
          <select value={choice} onChange={(e) => onChoice(e.target.value as SuggestChoice)} style={selectStyle}>
            <option value="skip">Пропустить</option>
            <option value="merge">Слить</option>
            <option value="create">Создать новый</option>
          </select>
        ) : (
          <span style={{ color: '#aaa' }}>—</span>
        )}
      </td>
    </tr>
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
  padding: '0.75rem 1rem',
  borderRadius: 6,
  marginBottom: '1.25rem',
  fontSize: '0.9rem',
  border: '1px solid',
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
const cancelBtn: React.CSSProperties = {
  padding: '0.5rem 1.2rem',
  background: 'transparent',
  color: '#555',
  border: '1px solid #ccc',
  borderRadius: 4,
  cursor: 'pointer',
};
const selectStyle: React.CSSProperties = {
  padding: '0.3rem 0.5rem',
  border: '1px solid #ccc',
  borderRadius: 4,
  fontSize: '0.85rem',
};
