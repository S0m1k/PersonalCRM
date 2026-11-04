'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { Plus, Sparkles, X } from 'lucide-react';
import type { Contact } from '@/lib/api';
import { createGroup, groupsKey, tagsKey, type Group, type TagCount } from '@/lib/api-crm';
import { errorText, fullName } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { ChipInput } from '@/components/contact/chip-input';
import { EditableText } from '@/components/contact/editable';
import type { SaveContact } from '@/components/contact/types';
import { Card, CardAction, CardHeader } from '@/components/ui/card';
import { Popover, PopoverContent, PopoverTrigger, Tooltip } from '@/components/ui/overlays';

type CardProps = { contact: Contact; onSave: SaveContact };

function useDebounced(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

function RelatedRow({ contactId, label, onLabel, onRemove }: { contactId: string; label: string; onLabel: (v: string) => void; onRemove: () => void }) {
  const { data: other, error } = useSWR<Contact>(`/api/contacts/${contactId}`);
  const name = other ? fullName(other) || 'Без имени' : error ? 'Контакт удалён' : '…';
  return (
    <li className="group flex items-center gap-2">
      <Avatar name={name} size="md" />
      <div className="min-w-0 flex-1">
        {other ? (
          <Link href={`/contacts/${contactId}`} className="block truncate text-sm font-medium hover:underline">
            {name}
          </Link>
        ) : (
          <span className="block truncate text-sm text-faint">{name}</span>
        )}
        <EditableText value={label} onCommit={onLabel} placeholder="Кем приходится…" ariaLabel={`Связь с ${name}`} className="-mx-2 min-h-6 text-xs text-muted" />
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="rounded p-1 text-faint opacity-0 hover:bg-hover hover:text-fg focus-visible:opacity-100 group-hover:opacity-100"
        aria-label={`Убрать связь с ${name}`}
      >
        <X className="size-3.5" />
      </button>
    </li>
  );
}

export function RelatedCard({ contact, onSave }: CardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState('');
  const q = useDebounced(query.trim(), 150);
  const { data: found = [] } = useSWR<Contact[]>(isOpen ? `/api/contacts/?limit=8${q ? `&q=${encodeURIComponent(q)}` : ''}` : null, {
    keepPreviousData: true,
  });
  const linked = new Set(contact.relationships.map((r) => r.contact_id));
  const options = found.filter((c) => c.id !== contact.id && !linked.has(c.id));

  function add(other: Contact) {
    setIsOpen(false);
    setQuery('');
    void onSave({ relationships: [...contact.relationships, { contact_id: other.id, label: '' }] });
  }

  return (
    <Card>
      <CardHeader
        label="Связанные контакты"
        action={
          <Popover open={isOpen} onOpenChange={setIsOpen}>
            <PopoverTrigger asChild>
              <CardAction aria-label="Добавить связанный контакт">Добавить</CardAction>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-64">
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Найти контакт…"
                aria-label="Поиск контакта"
                className="mb-1 h-8 w-full rounded-lg border border-line bg-transparent px-2 text-sm outline-none focus:border-accent"
              />
              {options.length === 0 && <p className="px-2 py-2 text-sm text-faint">Никого не найдено</p>}
              {options.map((c) => (
                <button key={c.id} type="button" onClick={() => add(c)} className="flex h-9 w-full items-center gap-2 rounded-lg px-2 text-left text-sm hover:bg-hover">
                  <Avatar name={fullName(c) || '?'} size="sm" />
                  <span className="truncate">{fullName(c) || 'Без имени'}</span>
                </button>
              ))}
            </PopoverContent>
          </Popover>
        }
      />
      {contact.relationships.length === 0 ? (
        <p className="text-sm text-faint">Супруг, коллега, друг — добавьте, кем вам приходятся люди.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {contact.relationships.map((rel, index) => (
            <RelatedRow
              key={rel.contact_id}
              contactId={rel.contact_id}
              label={rel.label}
              onLabel={(label) => void onSave({ relationships: contact.relationships.map((r, i) => (i === index ? { ...r, label } : r)) })}
              onRemove={() => void onSave({ relationships: contact.relationships.filter((_, i) => i !== index) })}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

export function GroupsCard({ contact, onSave }: CardProps) {
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());
  const { mutate } = useSWRConfig();
  const [isOpen, setIsOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const mine = groups.filter((g) => contact.group_ids.includes(g.id));
  const available = groups.filter((g) => !contact.group_ids.includes(g.id));

  function attach(id: string) {
    setIsOpen(false);
    void onSave({ group_ids: [...contact.group_ids, id] });
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    const name = draft.trim();
    if (!name) return;
    try {
      const group = await createGroup({ name });
      setDraft('');
      await mutate(groupsKey());
      attach(group.id);
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <Card>
      <CardHeader
        label="Группы"
        action={
          <Popover open={isOpen} onOpenChange={setIsOpen}>
            <PopoverTrigger asChild>
              <CardAction aria-label="Добавить в группу">Добавить</CardAction>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-64">
              {available.map((g) => (
                <button key={g.id} type="button" onClick={() => attach(g.id)} className="flex h-8 w-full items-center gap-2 rounded-lg px-2 text-left text-sm hover:bg-hover">
                  <span aria-hidden>{g.emoji}</span> <span className="truncate">{g.name}</span>
                </button>
              ))}
              <form onSubmit={(e) => void handleCreate(e)} className="mt-1 flex gap-1 border-t border-line px-1 pt-2">
                <input
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="Новая группа…"
                  aria-label="Название новой группы"
                  className="h-8 min-w-0 flex-1 rounded-lg border border-line bg-transparent px-2 text-sm outline-none focus:border-accent"
                />
                <button type="submit" aria-label="Создать группу" className="flex size-8 items-center justify-center rounded-lg text-accent hover:bg-hover">
                  <Plus className="size-4" />
                </button>
              </form>
            </PopoverContent>
          </Popover>
        }
      />
      {mine.length === 0 ? (
        <p className="text-sm text-faint">Не состоит ни в одной группе.</p>
      ) : (
        <ul className="flex flex-wrap gap-1.5">
          {mine.map((g) => (
            <li key={g.id} className="inline-flex h-7 items-center gap-1.5 rounded-full border border-line bg-surface pl-2.5 pr-1.5 text-[13px]">
              <span aria-hidden>{g.emoji}</span> {g.name}
              <button
                type="button"
                onClick={() => void onSave({ group_ids: contact.group_ids.filter((id) => id !== g.id) })}
                className="rounded-full p-0.5 text-faint hover:bg-hover hover:text-fg"
                aria-label={`Убрать из группы «${g.name}»`}
              >
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function TagsCard({ contact, onSave }: CardProps) {
  const { data: allTags = [] } = useSWR<TagCount[]>(tagsKey());
  return (
    <Card>
      <CardHeader
        label="Теги"
        action={
          <Tooltip label="Скоро: ИИ предложит теги по карточке" side="left">
            <span>
              <button
                type="button"
                disabled
                aria-label="ИИ-автотеги (скоро)"
                className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase leading-none tracking-[0.08em] text-faint"
              >
                <Sparkles className="size-3" /> ИИ-автотеги
              </button>
            </span>
          </Tooltip>
        }
      />
      <ChipInput
        values={contact.tags}
        onChange={(tags) => void onSave({ tags })}
        suggestions={allTags.map((t) => t.tag)}
        placeholder="Добавить тег…"
        ariaLabel="Новый тег"
        emptyText="Тегов пока нет."
      />
    </Card>
  );
}
