'use client';

import {
  AlignLeft,
  AtSign,
  Briefcase,
  Building2,
  Cake,
  Calendar,
  Hash,
  Home,
  Info,
  LayoutTemplate,
  Link2,
  ListChecks,
  MapPin,
  Phone,
  Plus,
  SquareCheck,
  Tag as TagIcon,
  Type,
  X,
  type LucideIcon,
} from 'lucide-react';
import type { Contact, CustomField, FieldType, FieldValue, Template } from '@/lib/api';
import { formatDate } from '@/lib/utils';
import { TemplateIcon } from '@/components/app/icons';
import { EditableText, FieldValueEditor, PropertyRow, SelectValue } from '@/components/contact/editable';
import { MultiValue } from '@/components/contact/multi-value';
import type { SaveContact } from '@/components/contact/types';
import { Card, CardHeader } from '@/components/ui/card';
import { Tag } from '@/components/ui/tag';

type CardProps = { contact: Contact; onSave: SaveContact };

const FIELD_ICONS: Record<FieldType, LucideIcon> = {
  text: Type,
  longtext: AlignLeft,
  date: Calendar,
  number: Hash,
  select: ListChecks,
  url: Link2,
  bool: SquareCheck,
};

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Вручную',
  outlook: 'Outlook',
  google: 'Google',
  csv: 'CSV',
  vcard: 'vCard',
  telegram: 'Telegram',
  phone: 'Телефон',
};

export function ContactInfoCard({ contact, onSave }: CardProps) {
  return (
    <Card id="data-contact-info" className="scroll-mt-24">
      <CardHeader label="Контактная информация" />
      <div className="flex flex-col gap-px">
        <PropertyRow icon={<Phone />} label="Телефоны">
          <MultiValue kind="tel" defaultLabel="мобильный" items={contact.phones} onChange={(phones) => void onSave({ phones })} />
        </PropertyRow>
        <PropertyRow icon={<AtSign />} label="Почта">
          <MultiValue kind="email" defaultLabel="email" items={contact.emails} onChange={(emails) => void onSave({ emails })} />
        </PropertyRow>
        <PropertyRow icon={<Home />} label="Адрес">
          <EditableText value={contact.address} onCommit={(v) => void onSave({ address: v })} ariaLabel="Адрес" />
        </PropertyRow>
        <PropertyRow icon={<MapPin />} label="Город">
          <EditableText value={contact.city} onCommit={(v) => void onSave({ city: v })} ariaLabel="Город" />
        </PropertyRow>
        <PropertyRow icon={<Cake />} label="День рождения">
          <EditableText
            type="date"
            value={contact.birthday ?? ''}
            display={formatDate(contact.birthday)}
            onCommit={(v) => void onSave({ birthday: v || null })}
            ariaLabel="День рождения"
          />
        </PropertyRow>
        <PropertyRow icon={<Building2 />} label="Компания">
          <EditableText value={contact.company} onCommit={(v) => void onSave({ company: v })} ariaLabel="Компания" />
        </PropertyRow>
        <PropertyRow icon={<Briefcase />} label="Должность">
          <EditableText value={contact.position} onCommit={(v) => void onSave({ position: v })} ariaLabel="Должность" />
        </PropertyRow>
        <PropertyRow icon={<TagIcon />} label="Категория">
          <EditableText value={contact.category} onCommit={(v) => void onSave({ category: v })} ariaLabel="Категория" />
        </PropertyRow>
      </div>
    </Card>
  );
}

export function TemplateCard({ contact, templates, onSave }: CardProps & { templates: Template[] }) {
  const template = templates.find((t) => t.id === contact.template_id);

  function saveField(key: string, value: FieldValue | '') {
    const fields = { ...contact.fields };
    if (value === '') delete fields[key];
    else fields[key] = value;
    void onSave({ fields });
  }

  return (
    <Card>
      <CardHeader label="Шаблон" />
      <PropertyRow icon={<LayoutTemplate />} label="Шаблон">
        <SelectValue
          value={contact.template_id ?? ''}
          options={templates.map((t) => t.id)}
          placeholder="Без шаблона"
          renderOption={(tid) => {
            const t = templates.find((x) => x.id === tid);
            return t ? (
              <Tag>
                <TemplateIcon name={t.icon} className="size-3" /> {t.name}
              </Tag>
            ) : (
              <Tag>—</Tag>
            );
          }}
          onCommit={(tid) => void onSave({ template_id: tid })}
        />
      </PropertyRow>
      {template && template.fields.length > 0 && (
        <div className="mt-2 border-t border-line pt-2">
          {template.fields.map((def) => {
            const Icon = FIELD_ICONS[def.type];
            return (
              <PropertyRow key={def.key} icon={<Icon />} label={def.label}>
                <FieldValueEditor def={def} value={contact.fields[def.key]} onCommit={(v) => saveField(def.key, v)} />
              </PropertyRow>
            );
          })}
        </div>
      )}
    </Card>
  );
}

export function CustomFieldsCard({ contact, onSave }: CardProps) {
  const fields = contact.custom_fields;
  const change = (next: CustomField[]) => void onSave({ custom_fields: next });
  const update = (index: number, patch: Partial<CustomField>) => change(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));

  return (
    <Card>
      <CardHeader label="Свои поля" />
      {fields.map((field, index) => (
        <div key={index} className="group grid grid-cols-[96px_1fr_auto] items-start gap-1 sm:grid-cols-[minmax(100px,140px)_1fr_auto]">
          <EditableText
            value={field.key}
            onCommit={(key) => update(index, { key: key || 'Поле' })}
            ariaLabel="Название поля"
            className="text-muted"
            display={
              <span className="flex items-center gap-2 text-muted">
                <Hash className="size-4 text-faint" />
                <span className="truncate">{field.key}</span>
              </span>
            }
          />
          <EditableText value={field.value} onCommit={(value) => update(index, { value })} ariaLabel={field.key} />
          <button
            type="button"
            onClick={() => change(fields.filter((_, i) => i !== index))}
            className="mt-1.5 rounded p-0.5 text-faint opacity-0 hover:bg-hover hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
            aria-label={`Удалить поле ${field.key}`}
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => change([...fields, { key: 'Новое поле', value: '' }])}
        className="flex h-8 items-center gap-2 rounded px-1 text-sm text-faint hover:bg-hover hover:text-muted"
      >
        <Plus className="size-4" /> Добавить поле
      </button>
    </Card>
  );
}

export function SourcesCard({ contact }: { contact: Contact }) {
  const sources = contact.sources.length ? contact.sources : [contact.source];
  const linked = [contact.external_ids.outlook && 'Outlook', contact.external_ids.google && 'Google'].filter(Boolean) as string[];
  return (
    <Card>
      <CardHeader label="Источники" />
      <PropertyRow icon={<Info />} label="Откуда">
        <div className="flex min-h-8 flex-wrap items-center gap-1 px-2">
          {sources.map((s) => (
            <Tag key={s}>{SOURCE_LABELS[s] ?? s}</Tag>
          ))}
        </div>
      </PropertyRow>
      <PropertyRow icon={<Info />} label="Связан с">
        <div className="flex min-h-8 flex-wrap items-center gap-1 px-2 text-sm">
          {linked.length ? linked.map((l) => <Tag key={l} color={l === 'Outlook' ? 'blue' : 'green'}>{l}</Tag>) : <span className="text-faint">Только в CRM</span>}
        </div>
      </PropertyRow>
      <PropertyRow icon={<Info />} label="Создан">
        <div className="flex min-h-8 items-center px-2 text-sm">{new Date(contact.created_at).toLocaleString('ru-RU')}</div>
      </PropertyRow>
      <PropertyRow icon={<Info />} label="Синхронизирован">
        <div className="flex min-h-8 items-center px-2 text-sm">
          {contact.last_synced_at ? new Date(contact.last_synced_at).toLocaleString('ru-RU') : <span className="text-faint">—</span>}
        </div>
      </PropertyRow>
    </Card>
  );
}
