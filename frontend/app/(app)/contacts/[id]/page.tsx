'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import {
  AtSign,
  Briefcase,
  Building2,
  Cake,
  ChevronRight,
  CircleHelp,
  Flag,
  Hash,
  Info,
  LayoutTemplate,
  MapPin,
  MoreHorizontal,
  Phone,
  Plus,
  StickyNote,
  Tag as TagIcon,
  Trash2,
  X,
} from 'lucide-react';
import {
  deleteContact,
  updateContact,
  type Contact,
  type ContactUpdate,
  type CustomField,
  type FieldType,
  type FieldValue,
  type Template,
} from '@/lib/api';
import { errorText, formatDate, fullName, relativeTime, type TagColor } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { EmptyState, Page, SectionTitle, Skeleton } from '@/components/app/page';
import { EditableText, FieldValueEditor, PropertyRow, SelectValue } from '@/components/contact/editable';
import { MultiValue } from '@/components/contact/multi-value';
import { QuestionsPanel } from '@/components/contact/questions-panel';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  Menu,
  MenuContent,
  MenuItem,
  MenuTrigger,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/overlays';
import { Tag } from '@/components/ui/tag';

const PRIORITIES: Record<string, { label: string; color: TagColor }> = {
  high: { label: 'Высокий', color: 'red' },
  medium: { label: 'Средний', color: 'yellow' },
  low: { label: 'Низкий', color: 'gray' },
};

const FIELD_ICONS: Record<FieldType, string> = {
  text: 'Aa',
  longtext: '¶',
  date: '📅',
  number: '#',
  select: '▾',
  url: '🔗',
  bool: '☑',
};

const SOURCE_LABELS: Record<string, string> = {
  manual: 'Вручную',
  outlook: 'Outlook',
  google: 'Google',
  csv: 'CSV',
  vcard: 'vCard',
  telegram: 'Telegram',
};

export default function ContactPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { mutate: mutateGlobal } = useSWRConfig();
  const key = `/api/contacts/${id}`;
  const { data: contact, error, mutate } = useSWR<Contact>(key);
  const { data: templates = [] } = useSWR<Template[]>('/api/templates');
  const [isDeleteOpen, setIsDeleteOpen] = useState(false);

  async function save(patch: ContactUpdate) {
    if (!contact) return;
    try {
      const updated = await updateContact(contact.id, patch);
      await mutate(updated, { revalidate: false });
      void mutateGlobal((k) => typeof k === 'string' && (k.startsWith('/api/contacts/?') || k.startsWith('/api/home')));
    } catch (err) {
      toast.error(errorText(err));
      void mutate();
    }
  }

  async function handleDelete() {
    if (!contact) return;
    try {
      await deleteContact(contact.id);
      void mutateGlobal((k) => typeof k === 'string' && k.startsWith('/api/'));
      toast.success('Контакт удалён');
      router.push('/contacts');
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  if (error) {
    return (
      <Page>
        <EmptyState icon="🤷" title="Контакт не найден">
          Возможно, его удалили. <Link href="/contacts" className="underline">К списку контактов</Link>
        </EmptyState>
      </Page>
    );
  }

  if (!contact) {
    return (
      <Page>
        <Skeleton className="mb-6 size-[72px] rounded-full" />
        <Skeleton className="mb-8 h-10 w-2/3" />
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-8" />
          ))}
        </div>
      </Page>
    );
  }

  const name = fullName(contact);
  const template = templates.find((t) => t.id === contact.template_id);
  const subtitle = [contact.position, contact.company].filter(Boolean).join(' · ');

  function saveName(value: string) {
    const [first = '', ...rest] = value.split(/\s+/);
    void save({ first_name: first, last_name: rest.join(' ') });
  }

  function saveField(fieldKey: string, value: FieldValue | '') {
    const fields = { ...contact!.fields };
    if (value === '') delete fields[fieldKey];
    else fields[fieldKey] = value;
    void save({ fields });
  }

  return (
    <>
      <div className="sticky top-0 z-10 flex h-11 items-center gap-1 bg-bg/85 px-3 backdrop-blur">
        <Link href="/contacts" className="rounded px-1.5 py-0.5 text-sm text-muted hover:bg-hover hover:text-fg">
          Контакты
        </Link>
        <ChevronRight className="size-3.5 text-faint" />
        <span className="truncate px-1.5 text-sm">{name || 'Без имени'}</span>
        <span className="ml-auto mr-2 hidden text-xs text-faint sm:inline">Изменён {relativeTime(contact.updated_at)}</span>
        <Menu>
          <MenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Действия">
              <MoreHorizontal />
            </Button>
          </MenuTrigger>
          <MenuContent align="end">
            <MenuItem danger onSelect={() => setIsDeleteOpen(true)}>
              <Trash2 /> Удалить контакт
            </MenuItem>
          </MenuContent>
        </Menu>
      </div>

      <Page className="pt-8">
        <header className="mb-6 animate-fade-up">
          <Avatar name={name || '?'} size="xl" className="mb-4" />
          <EditableText
            value={name}
            onCommit={saveName}
            placeholder="Без имени"
            ariaLabel="Имя"
            className="-mx-2 min-h-[52px] text-title hover:bg-hover/60 [&_input]:text-title"
          />
          {subtitle && <p className="mt-1 text-[15px] text-muted">{subtitle}</p>}
        </header>

        <section className="mb-8 flex flex-col gap-px" aria-label="Свойства">
          <PropertyRow icon={<LayoutTemplate />} label="Шаблон">
            <SelectValue
              value={contact.template_id ?? ''}
              options={templates.map((t) => t.id)}
              placeholder="Без шаблона"
              renderOption={(tid) => {
                const t = templates.find((x) => x.id === tid);
                return t ? <Tag>{t.icon} {t.name}</Tag> : <Tag>—</Tag>;
              }}
              onCommit={(tid) => void save({ template_id: tid })}
            />
          </PropertyRow>
          <PropertyRow icon={<Building2 />} label="Компания">
            <EditableText value={contact.company} onCommit={(v) => void save({ company: v })} ariaLabel="Компания" />
          </PropertyRow>
          <PropertyRow icon={<Briefcase />} label="Должность">
            <EditableText value={contact.position} onCommit={(v) => void save({ position: v })} ariaLabel="Должность" />
          </PropertyRow>
          <PropertyRow icon={<Phone />} label="Телефон">
            <MultiValue kind="tel" defaultLabel="мобильный" items={contact.phones} onChange={(phones) => void save({ phones })} />
          </PropertyRow>
          <PropertyRow icon={<AtSign />} label="Почта">
            <MultiValue kind="email" defaultLabel="email" items={contact.emails} onChange={(emails) => void save({ emails })} />
          </PropertyRow>
          <PropertyRow icon={<MapPin />} label="Город">
            <EditableText value={contact.city} onCommit={(v) => void save({ city: v })} ariaLabel="Город" />
          </PropertyRow>
          <PropertyRow icon={<Cake />} label="День рождения">
            <EditableText
              type="date"
              value={contact.birthday ?? ''}
              display={formatDate(contact.birthday)}
              onCommit={(v) => void save({ birthday: v || null })}
              ariaLabel="День рождения"
            />
          </PropertyRow>
          <PropertyRow icon={<TagIcon />} label="Категория">
            <EditableText value={contact.category} onCommit={(v) => void save({ category: v })} ariaLabel="Категория" />
          </PropertyRow>
          <PropertyRow icon={<Flag />} label="Приоритет">
            <SelectValue
              value={contact.priority}
              options={Object.keys(PRIORITIES)}
              renderOption={(p) => <Tag color={PRIORITIES[p]?.color ?? 'gray'}>{PRIORITIES[p]?.label ?? p}</Tag>}
              onCommit={(v) => void save({ priority: v })}
            />
          </PropertyRow>

          {template && template.fields.length > 0 && (
            <div className="mt-3 border-t border-line pt-3">
              <div className="mb-1 px-1 text-xs font-medium text-faint">
                {template.icon} {template.name}
              </div>
              {template.fields.map((def) => (
                <PropertyRow key={def.key} icon={<span className="w-4 text-center text-xs">{FIELD_ICONS[def.type]}</span>} label={def.label}>
                  <FieldValueEditor def={def} value={contact.fields[def.key]} onCommit={(v) => saveField(def.key, v)} />
                </PropertyRow>
              ))}
            </div>
          )}

          <CustomFields fields={contact.custom_fields} onChange={(custom_fields) => void save({ custom_fields })} />
        </section>

        <Tabs defaultValue={searchParams.get('tab') ?? 'overview'}>
          <TabsList>
            <TabsTrigger value="overview">
              <StickyNote /> Заметки
            </TabsTrigger>
            <TabsTrigger value="questions">
              <CircleHelp /> Вопросы
            </TabsTrigger>
            <TabsTrigger value="sources">
              <Info /> Источники
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="pt-4">
            <EditableText
              isMultiline
              value={contact.notes}
              onCommit={(v) => void save({ notes: v })}
              placeholder="Пишите здесь всё, что важно помнить: о чём говорили, договорённости, детали…"
              ariaLabel="Заметки"
              className="min-h-24"
            />
            <div className="mt-8">
              <SectionTitle>Открытые вопросы</SectionTitle>
              <QuestionsPanel contactId={contact.id} isCompact />
            </div>
          </TabsContent>

          <TabsContent value="questions" className="pt-4">
            <QuestionsPanel contactId={contact.id} />
          </TabsContent>

          <TabsContent value="sources" className="pt-4">
            <SourcesInfo contact={contact} />
          </TabsContent>
        </Tabs>
      </Page>

      <Dialog open={isDeleteOpen} onOpenChange={setIsDeleteOpen}>
        <DialogContent title={`Удалить «${name || 'Без имени'}»?`} description="Вместе с контактом удалятся его вопросы. Отменить нельзя.">
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setIsDeleteOpen(false)}>
              Отмена
            </Button>
            <Button variant="primary" className="bg-danger hover:bg-danger/90" onClick={handleDelete}>
              Удалить
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

function CustomFields({ fields, onChange }: { fields: CustomField[]; onChange: (fields: CustomField[]) => void }) {
  function update(index: number, patch: Partial<CustomField>) {
    onChange(fields.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  return (
    <div className="mt-1">
      {fields.map((field, index) => (
        <div key={index} className="group grid grid-cols-[96px_1fr_auto] items-start gap-1 sm:grid-cols-[minmax(120px,170px)_1fr_auto]">
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
            onClick={() => onChange(fields.filter((_, i) => i !== index))}
            className="mt-1.5 rounded p-0.5 text-faint opacity-0 hover:bg-hover hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
            aria-label={`Удалить поле ${field.key}`}
          >
            <X className="size-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...fields, { key: 'Новое поле', value: '' }])}
        className="flex h-8 items-center gap-2 rounded px-1 text-sm text-faint hover:bg-hover hover:text-muted"
      >
        <Plus className="size-4" /> Добавить свойство
      </button>
    </div>
  );
}

function SourcesInfo({ contact }: { contact: Contact }) {
  const sources = contact.sources.length ? contact.sources : [contact.source];
  return (
    <div className="flex flex-col gap-px">
      <PropertyRow icon={<Info />} label="Откуда">
        <div className="flex min-h-8 flex-wrap items-center gap-1 px-2">
          {sources.map((s) => (
            <Tag key={s} color="gray">
              {SOURCE_LABELS[s] ?? s}
            </Tag>
          ))}
        </div>
      </PropertyRow>
      <PropertyRow icon={<Info />} label="Связан с">
        <div className="flex min-h-8 flex-wrap items-center gap-1 px-2 text-sm">
          {contact.external_ids.outlook && <Tag color="blue">Outlook</Tag>}
          {contact.external_ids.google && <Tag color="green">Google</Tag>}
          {!contact.external_ids.outlook && !contact.external_ids.google && <span className="text-faint">Только в CRM</span>}
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
    </div>
  );
}
