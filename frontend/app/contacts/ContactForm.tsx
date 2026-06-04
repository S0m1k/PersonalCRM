'use client';

/**
 * Форма создания / редактирования контакта.
 * Используется на страницах /contacts/new и /contacts/[id].
 *
 * Поддерживает динамическое добавление/удаление телефонов и email-адресов.
 */

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  createContact,
  updateContact,
  type Contact,
  type ContactCreate,
  type CustomField,
} from '../../lib/api';

interface Props {
  /** Если передан — режим редактирования, иначе — создание. */
  existing?: Contact;
}

interface PhoneRow {
  value: string;
  label: string;
}

interface EmailRow {
  value: string;
  label: string;
}

export default function ContactForm({ existing }: Props) {
  const router = useRouter();
  const isEdit = !!existing;

  const [firstName, setFirstName] = useState(existing?.first_name ?? '');
  const [lastName, setLastName] = useState(existing?.last_name ?? '');
  const [company, setCompany] = useState(existing?.company ?? '');
  const [position, setPosition] = useState(existing?.position ?? '');
  const [city, setCity] = useState(existing?.city ?? '');
  const [birthday, setBirthday] = useState(existing?.birthday ?? '');
  const [notes, setNotes] = useState(existing?.notes ?? '');
  const [category, setCategory] = useState(existing?.category ?? '');
  const [priority, setPriority] = useState(existing?.priority ?? '');

  const [phones, setPhones] = useState<PhoneRow[]>(
    existing?.phones?.length ? existing.phones : [{ value: '', label: 'мобильный' }],
  );
  const [emails, setEmails] = useState<EmailRow[]>(
    existing?.emails?.length ? existing.emails : [{ value: '', label: 'личный' }],
  );
  const [customFields, setCustomFields] = useState<CustomField[]>(
    existing?.custom_fields ?? [],
  );

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Helpers for phone/email arrays
  function setPhone(index: number, field: 'value' | 'label', val: string) {
    setPhones((prev) => prev.map((p, i) => (i === index ? { ...p, [field]: val } : p)));
  }

  function addPhone() {
    setPhones((prev) => [...prev, { value: '', label: 'мобильный' }]);
  }

  function removePhone(index: number) {
    setPhones((prev) => prev.filter((_, i) => i !== index));
  }

  function setEmail(index: number, field: 'value' | 'label', val: string) {
    setEmails((prev) => prev.map((e, i) => (i === index ? { ...e, [field]: val } : e)));
  }

  function addEmail() {
    setEmails((prev) => [...prev, { value: '', label: 'личный' }]);
  }

  function removeEmail(index: number) {
    setEmails((prev) => prev.filter((_, i) => i !== index));
  }

  // Произвольные поля (custom_fields)
  function setCustomField(index: number, field: 'key' | 'value', val: string) {
    setCustomFields((prev) => prev.map((cf, i) => (i === index ? { ...cf, [field]: val } : cf)));
  }

  function addCustomField() {
    setCustomFields((prev) => [...prev, { key: '', value: '' }]);
  }

  function removeCustomField(index: number) {
    setCustomFields((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);

    const payload: ContactCreate = {
      first_name: firstName,
      last_name: lastName,
      company,
      position,
      city,
      birthday: birthday || null,
      notes,
      category,
      priority,
      phones: phones.filter((p) => p.value.trim()),
      emails: emails.filter((em) => em.value.trim()),
      custom_fields: customFields.filter((cf) => cf.key.trim()),
    };

    try {
      if (isEdit && existing) {
        await updateContact(existing.id, payload);
        router.push(`/contacts/${existing.id}`);
      } else {
        const created = await createContact(payload);
        router.push(`/contacts/${created.id}`);
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.message === 'Не авторизован') {
        router.push('/login');
        return;
      }
      setError('Ошибка при сохранении. Попробуйте ещё раз.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} style={formStyle}>
      {/* Имя / Фамилия */}
      <div style={rowStyle}>
        <Field label="Имя">
          <input value={firstName} onChange={(e) => setFirstName(e.target.value)} style={inputStyle} placeholder="Имя" />
        </Field>
        <Field label="Фамилия">
          <input value={lastName} onChange={(e) => setLastName(e.target.value)} style={inputStyle} placeholder="Фамилия" />
        </Field>
      </div>

      {/* Компания / Должность */}
      <div style={rowStyle}>
        <Field label="Компания">
          <input value={company} onChange={(e) => setCompany(e.target.value)} style={inputStyle} placeholder="Название компании" />
        </Field>
        <Field label="Должность">
          <input value={position} onChange={(e) => setPosition(e.target.value)} style={inputStyle} placeholder="Должность" />
        </Field>
      </div>

      {/* Город / Дата рождения */}
      <div style={rowStyle}>
        <Field label="Город">
          <input value={city} onChange={(e) => setCity(e.target.value)} style={inputStyle} placeholder="Город" />
        </Field>
        <Field label="Дата рождения">
          <input
            type="date"
            value={birthday}
            onChange={(e) => setBirthday(e.target.value)}
            style={inputStyle}
          />
        </Field>
      </div>

      {/* Категория / Приоритет */}
      <div style={rowStyle}>
        <Field label="Категория">
          <input value={category} onChange={(e) => setCategory(e.target.value)} style={inputStyle} placeholder="клиент, коллега, друг…" />
        </Field>
        <Field label="Приоритет">
          <select value={priority} onChange={(e) => setPriority(e.target.value)} style={inputStyle}>
            <option value="">—</option>
            <option value="high">Высокий</option>
            <option value="medium">Средний</option>
            <option value="low">Низкий</option>
          </select>
        </Field>
      </div>

      {/* Телефоны */}
      <fieldset style={fieldsetStyle}>
        <legend style={legendStyle}>Телефоны</legend>
        {phones.map((p, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
            <input
              value={p.value}
              onChange={(e) => setPhone(i, 'value', e.target.value)}
              placeholder="+7 900 000 00 00"
              style={{ ...inputStyle, flex: 2 }}
            />
            <input
              value={p.label}
              onChange={(e) => setPhone(i, 'label', e.target.value)}
              placeholder="мобильный"
              style={{ ...inputStyle, flex: 1 }}
            />
            {phones.length > 1 && (
              <button type="button" onClick={() => removePhone(i)} style={removeBtn}>×</button>
            )}
          </div>
        ))}
        <button type="button" onClick={addPhone} style={addBtn}>+ Добавить телефон</button>
      </fieldset>

      {/* Email */}
      <fieldset style={fieldsetStyle}>
        <legend style={legendStyle}>Email-адреса</legend>
        {emails.map((em, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
            <input
              type="email"
              value={em.value}
              onChange={(e) => setEmail(i, 'value', e.target.value)}
              placeholder="email@example.com"
              style={{ ...inputStyle, flex: 2 }}
            />
            <input
              value={em.label}
              onChange={(e) => setEmail(i, 'label', e.target.value)}
              placeholder="личный"
              style={{ ...inputStyle, flex: 1 }}
            />
            {emails.length > 1 && (
              <button type="button" onClick={() => removeEmail(i)} style={removeBtn}>×</button>
            )}
          </div>
        ))}
        <button type="button" onClick={addEmail} style={addBtn}>+ Добавить email</button>
      </fieldset>

      {/* Свои поля (custom_fields) */}
      <fieldset style={fieldsetStyle}>
        <legend style={legendStyle}>Свои поля</legend>
        {customFields.length === 0 && (
          <p style={{ margin: '0 0 0.5rem', fontSize: '0.85rem', color: '#888' }}>
            Произвольные пары «название → значение» (например: «Telegram → @ivan», «Хобби → рыбалка»).
          </p>
        )}
        {customFields.map((cf, i) => (
          <div key={i} style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'center' }}>
            <input
              value={cf.key}
              onChange={(e) => setCustomField(i, 'key', e.target.value)}
              placeholder="Название поля"
              style={{ ...inputStyle, flex: 1 }}
            />
            <input
              value={cf.value}
              onChange={(e) => setCustomField(i, 'value', e.target.value)}
              placeholder="Значение"
              style={{ ...inputStyle, flex: 2 }}
            />
            <button type="button" onClick={() => removeCustomField(i)} style={removeBtn}>×</button>
          </div>
        ))}
        <button type="button" onClick={addCustomField} style={addBtn}>+ Добавить своё поле</button>
      </fieldset>

      {/* Заметки */}
      <Field label="Заметки">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={4}
          style={{ ...inputStyle, resize: 'vertical', width: '100%' }}
          placeholder="Произвольные заметки о контакте"
        />
      </Field>

      {error && <p style={{ color: '#c00', margin: 0 }}>{error}</p>}

      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
        <button type="submit" disabled={saving} style={submitBtn}>
          {saving ? 'Сохранение…' : isEdit ? 'Сохранить изменения' : 'Создать контакт'}
        </button>
        <button type="button" onClick={() => router.back()} style={cancelBtn}>
          Отмена
        </button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// Мелкие компоненты
// ---------------------------------------------------------------------------

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1 }}>
      <span style={{ fontWeight: 600, fontSize: '0.85rem', color: '#444' }}>{label}</span>
      {children}
    </label>
  );
}

// ---------------------------------------------------------------------------
// Стили
// ---------------------------------------------------------------------------

const formStyle: React.CSSProperties = {
  background: '#fff',
  padding: '2rem',
  borderRadius: 8,
  boxShadow: '0 1px 4px rgba(0,0,0,0.08)',
  display: 'flex',
  flexDirection: 'column',
  gap: '1.2rem',
};

const rowStyle: React.CSSProperties = {
  display: 'flex',
  gap: '1rem',
  flexWrap: 'wrap',
};

const inputStyle: React.CSSProperties = {
  padding: '0.5rem 0.7rem',
  border: '1px solid #ccc',
  borderRadius: 4,
  fontSize: '0.95rem',
  width: '100%',
  boxSizing: 'border-box',
};

const fieldsetStyle: React.CSSProperties = {
  border: '1px solid #e0e0e0',
  borderRadius: 6,
  padding: '0.75rem 1rem',
};

const legendStyle: React.CSSProperties = {
  fontWeight: 600,
  fontSize: '0.85rem',
  color: '#444',
  padding: '0 0.25rem',
};

const removeBtn: React.CSSProperties = {
  background: '#fee2e2',
  color: '#b91c1c',
  border: 'none',
  borderRadius: 4,
  cursor: 'pointer',
  fontWeight: 700,
  padding: '0.3rem 0.6rem',
};

const addBtn: React.CSSProperties = {
  background: 'transparent',
  color: '#2563eb',
  border: 'none',
  cursor: 'pointer',
  fontSize: '0.85rem',
  padding: 0,
  textDecoration: 'underline',
};

const submitBtn: React.CSSProperties = {
  padding: '0.6rem 1.5rem',
  background: '#2563eb',
  color: '#fff',
  border: 'none',
  borderRadius: 4,
  fontWeight: 600,
  cursor: 'pointer',
  fontSize: '0.95rem',
};

const cancelBtn: React.CSSProperties = {
  padding: '0.6rem 1.5rem',
  background: 'transparent',
  color: '#555',
  border: '1px solid #ccc',
  borderRadius: 4,
  cursor: 'pointer',
  fontSize: '0.95rem',
};
