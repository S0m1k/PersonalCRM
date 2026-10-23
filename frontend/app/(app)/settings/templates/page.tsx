'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, Plus, Trash2 } from 'lucide-react';
import { createTemplate, deleteTemplate, updateTemplate, type FieldDef, type FieldType, type Template } from '@/lib/api';
import { cn, errorText } from '@/lib/utils';
import { Page, PageHeader, Skeleton } from '@/components/app/page';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/overlays';

const TYPES: { value: FieldType; label: string }[] = [
  { value: 'text', label: 'Текст' },
  { value: 'longtext', label: 'Длинный текст' },
  { value: 'date', label: 'Дата' },
  { value: 'number', label: 'Число' },
  { value: 'select', label: 'Список вариантов' },
  { value: 'url', label: 'Ссылка' },
  { value: 'bool', label: 'Да / нет' },
];

type DraftField = FieldDef & { optionsText: string };
type Draft = { name: string; icon: string; fields: DraftField[] };

function toDraft(t: Template): Draft {
  return { name: t.name, icon: t.icon, fields: t.fields.map((f) => ({ ...f, optionsText: f.options.join(', ') })) };
}

function fromDraft(d: Draft) {
  return {
    name: d.name.trim(),
    icon: d.icon.trim() || '📄',
    fields: d.fields.map(({ optionsText, ...f }) => ({
      ...f,
      label: f.label.trim(),
      options: f.type === 'select' ? optionsText.split(',').map((o) => o.trim()).filter(Boolean) : [],
    })),
  };
}

export default function TemplatesPage() {
  const { data: templates, mutate } = useSWR<Template[]>('/api/templates');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = templates?.find((t) => t.id === selectedId) ?? templates?.[0];

  async function handleCreate() {
    try {
      const created = await createTemplate({ name: 'Новый шаблон', icon: '📄', fields: [{ label: 'Заметка', type: 'text', options: [] }] });
      await mutate();
      setSelectedId(created.id);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <Page wide>
      <PageHeader
        icon="🧩"
        title="Шаблоны карточек"
        description="Шаблон задаёт дополнительные поля карточки: у клиента — стадия и бюджет, у друга — семья и идеи подарков."
      />
      <div className="grid gap-8 md:grid-cols-[220px_1fr]">
        <nav className="flex flex-col gap-px" aria-label="Шаблоны">
          {!templates
            ? Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="mb-1 h-8" />)
            : templates.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setSelectedId(t.id)}
                  className={cn(
                    'flex h-8 items-center gap-2 rounded px-2 text-left text-sm transition-colors hover:bg-hover',
                    selected?.id === t.id && 'bg-hover font-medium',
                  )}
                >
                  <span aria-hidden>{t.icon}</span>
                  <span className="flex-1 truncate">{t.name}</span>
                  <span className="text-xs text-faint">{t.fields.length}</span>
                </button>
              ))}
          <button
            type="button"
            onClick={handleCreate}
            className="mt-1 flex h-8 items-center gap-2 rounded px-2 text-sm text-muted hover:bg-hover hover:text-fg"
          >
            <Plus className="size-4" /> Новый шаблон
          </button>
        </nav>

        {selected && (
          <TemplateEditor
            key={selected.id + selected.updated_at}
            template={selected}
            onSaved={() => void mutate()}
            onDeleted={() => {
              setSelectedId(null);
              void mutate();
            }}
          />
        )}
      </div>
    </Page>
  );
}

type EditorProps = {
  template: Template;
  onSaved: () => void;
  onDeleted: () => void;
};

function TemplateEditor({ template, onSaved, onDeleted }: EditorProps) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(template));
  const [isSaving, setIsSaving] = useState(false);
  const isDirty = JSON.stringify(fromDraft(draft)) !== JSON.stringify(fromDraft(toDraft(template)));

  useEffect(() => setDraft(toDraft(template)), [template]);

  function updateField(index: number, patch: Partial<DraftField>) {
    setDraft((d) => ({ ...d, fields: d.fields.map((f, i) => (i === index ? { ...f, ...patch } : f)) }));
  }

  function moveField(index: number, delta: -1 | 1) {
    setDraft((d) => {
      const fields = [...d.fields];
      const target = index + delta;
      [fields[index], fields[target]] = [fields[target], fields[index]];
      return { ...d, fields };
    });
  }

  async function handleSave() {
    setIsSaving(true);
    try {
      await updateTemplate(template.id, fromDraft(draft));
      toast.success('Шаблон сохранён');
      onSaved();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete() {
    try {
      await deleteTemplate(template.id);
      toast.success('Шаблон удалён');
      onDeleted();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <div className="animate-fade-up">
      <div className="mb-6 flex items-center gap-2">
        <Input
          value={draft.icon}
          onChange={(e) => setDraft({ ...draft, icon: e.target.value })}
          className="h-10 w-12 text-center text-xl"
          aria-label="Иконка"
          maxLength={8}
        />
        <Input
          value={draft.name}
          onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          className="h-10 flex-1 text-lg font-semibold"
          aria-label="Название шаблона"
        />
      </div>

      <div className="mb-2 grid grid-cols-[1fr_170px_80px] gap-2 px-1 text-xs font-medium text-faint">
        <span>Поле</span>
        <span>Тип</span>
        <span />
      </div>
      <div className="flex flex-col gap-2">
        {draft.fields.map((field, index) => (
          <div key={field.key || `new-${index}`} className="rounded-md border border-line p-2">
            <div className="grid grid-cols-[1fr_170px_80px] items-center gap-2">
              <Input value={field.label} onChange={(e) => updateField(index, { label: e.target.value })} aria-label="Название поля" />
              <Menu>
                <MenuTrigger asChild>
                  <Button variant="outline" className="justify-start font-normal">
                    {TYPES.find((t) => t.value === field.type)?.label}
                  </Button>
                </MenuTrigger>
                <MenuContent align="start">
                  {TYPES.map((t) => (
                    <MenuItem key={t.value} onSelect={() => updateField(index, { type: t.value })}>
                      {t.label}
                    </MenuItem>
                  ))}
                </MenuContent>
              </Menu>
              <div className="flex justify-end">
                <Button variant="ghost" size="icon" disabled={index === 0} onClick={() => moveField(index, -1)} aria-label="Выше">
                  <ArrowUp />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={index === draft.fields.length - 1}
                  onClick={() => moveField(index, 1)}
                  aria-label="Ниже"
                >
                  <ArrowDown />
                </Button>
                <Button
                  variant="danger"
                  size="icon"
                  onClick={() => setDraft((d) => ({ ...d, fields: d.fields.filter((_, i) => i !== index) }))}
                  aria-label="Удалить поле"
                >
                  <Trash2 />
                </Button>
              </div>
            </div>
            {field.type === 'select' && (
              <Input
                className="mt-2"
                value={field.optionsText}
                onChange={(e) => updateField(index, { optionsText: e.target.value })}
                placeholder="Варианты через запятую: Лид, Переговоры, Клиент"
                aria-label="Варианты списка"
              />
            )}
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => setDraft((d) => ({ ...d, fields: [...d.fields, { key: '', label: '', type: 'text', options: [], optionsText: '' }] }))}
        className="mt-2 flex h-8 items-center gap-2 rounded px-2 text-sm text-muted hover:bg-hover hover:text-fg"
      >
        <Plus className="size-4" /> Добавить поле
      </button>

      <div className="mt-8 flex items-center justify-between border-t border-line pt-4">
        <Button variant="danger" onClick={handleDelete}>
          <Trash2 /> Удалить шаблон
        </Button>
        <div className="flex gap-2">
          {isDirty && (
            <Button variant="ghost" onClick={() => setDraft(toDraft(template))}>
              Отменить
            </Button>
          )}
          <Button variant="primary" onClick={handleSave} disabled={!isDirty || isSaving}>
            {isSaving ? 'Сохраняю…' : 'Сохранить'}
          </Button>
        </div>
      </div>
      <p className="mt-3 text-xs text-faint">
        Удалённое поле пропадёт из карточек, но уже записанные значения сохранятся в базе.
      </p>
    </div>
  );
}
