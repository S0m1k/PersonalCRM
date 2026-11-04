'use client';

import Link from 'next/link';
import { Facebook, Globe, Instagram, Linkedin, Send, Twitter, type LucideIcon } from 'lucide-react';
import type { Contact, ContactUpdate } from '@/lib/api';
import type { Group } from '@/lib/api-crm';
import { socialHref, type ColumnId } from '@/lib/contact-view';
import { COLUMNS } from '@/lib/contact-view';
import { cn, formatDate, fullName, relativeTime } from '@/lib/utils';
import { Avatar } from '@/components/app/avatar';
import { Skeleton } from '@/components/app/page';
import { Tag } from '@/components/ui/tag';
import { EditableText, FrequencyCell, PriorityCell } from './inline-cells';

const SOCIAL_ICONS: Record<string, { icon: LucideIcon; label: string }> = {
  linkedin: { icon: Linkedin, label: 'LinkedIn' },
  facebook: { icon: Facebook, label: 'Facebook' },
  instagram: { icon: Instagram, label: 'Instagram' },
  telegram: { icon: Send, label: 'Telegram' },
  twitter: { icon: Twitter, label: 'X (Twitter)' },
  website: { icon: Globe, label: 'Сайт' },
};

const MAX_TAGS_SHOWN = 3;

type Props = {
  contacts: Contact[] | undefined;
  isLoading: boolean;
  columns: ColumnId[];
  groupsById: Map<string, Group>;
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
  onToggleAll: () => void;
  onUpdate: (id: string, patch: ContactUpdate) => void;
};

export function ContactsTable({ contacts, isLoading, columns, groupsById, selected, onToggle, onToggleAll, onUpdate }: Props) {
  const labels = new Map<string, string>(COLUMNS.map((c) => [c.id, c.label]));
  const isAllSelected = Boolean(contacts?.length) && contacts!.every((c) => selected.has(c.id));
  const isSomeSelected = !isAllSelected && Boolean(contacts?.some((c) => selected.has(c.id)));

  return (
    <div className="overflow-x-auto border-t border-line">
      <table className="w-full min-w-[760px] border-collapse text-sm">
        <thead>
          <tr className="text-left text-[13px] text-muted [&>th]:h-8 [&>th]:whitespace-nowrap [&>th]:border-b [&>th]:border-line [&>th]:px-2 [&>th]:font-normal">
            <th className="w-9">
              <input
                type="checkbox"
                aria-label="Выбрать все загруженные"
                checked={isAllSelected}
                ref={(el) => {
                  if (el) el.indeterminate = isSomeSelected;
                }}
                onChange={onToggleAll}
                className="size-4 accent-[rgb(var(--accent))]"
              />
            </th>
            <th className="min-w-[200px]">Имя</th>
            {columns.map((id) => (
              <th key={id}>{labels.get(id)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {isLoading && !contacts
            ? Array.from({ length: 8 }, (_, i) => (
                <tr key={i}>
                  <td colSpan={columns.length + 2} className="border-b border-line px-2 py-1.5">
                    <Skeleton className="h-6" />
                  </td>
                </tr>
              ))
            : contacts?.map((c) => (
                <Row
                  key={c.id}
                  contact={c}
                  columns={columns}
                  groupsById={groupsById}
                  isSelected={selected.has(c.id)}
                  onToggle={onToggle}
                  onUpdate={onUpdate}
                />
              ))}
        </tbody>
      </table>
    </div>
  );
}

function Row({
  contact: c,
  columns,
  groupsById,
  isSelected,
  onToggle,
  onUpdate,
}: {
  contact: Contact;
  columns: ColumnId[];
  groupsById: Map<string, Group>;
  isSelected: boolean;
  onToggle: (id: string) => void;
  onUpdate: (id: string, patch: ContactUpdate) => void;
}) {
  const name = fullName(c) || 'Без имени';
  const cells: Record<ColumnId, React.ReactNode> = {
    position: <EditableText value={c.position} label="Должность" placeholder="Добавить" onSave={(position) => onUpdate(c.id, { position })} />,
    company: <span className="block max-w-[200px] truncate">{c.company || <span className="text-faint">—</span>}</span>,
    frequency: (
      <FrequencyCell
        days={c.keep_in_touch.frequency_days}
        onChange={(days) => onUpdate(c.id, { keep_in_touch: { frequency_days: days, snoozed_until: c.keep_in_touch.snoozed_until } })}
      />
    ),
    priority: <PriorityCell value={c.priority} onChange={(priority) => onUpdate(c.id, { priority })} />,
    tags: <TagList tags={c.tags} />,
    groups: <GroupList ids={c.group_ids} groupsById={groupsById} />,
    social: <SocialIcons contact={c} />,
    last: c.last_interaction_at ? (
      <span className="text-muted" title={formatDate(c.last_interaction_at.slice(0, 10))}>{relativeTime(c.last_interaction_at)}</span>
    ) : (
      <span className="text-faint">Никогда</span>
    ),
    created: <span className="text-muted">{formatDate(c.created_at.slice(0, 10), false)}</span>,
  };

  return (
    <tr className={cn('group transition-colors hover:bg-hover/60 [&>td]:h-11 [&>td]:border-b [&>td]:border-line [&>td]:px-2', isSelected && 'bg-accent/5')}>
      <td>
        <input
          type="checkbox"
          aria-label={`Выбрать: ${name}`}
          checked={isSelected}
          onChange={() => onToggle(c.id)}
          className="size-4 accent-[rgb(var(--accent))]"
        />
      </td>
      <td>
        <Link href={`/contacts/${c.id}`} className="flex items-center gap-2.5">
          <Avatar name={name} size="md" />
          <span className="truncate font-medium group-hover:underline group-hover:decoration-line group-hover:underline-offset-4">{name}</span>
        </Link>
      </td>
      {columns.map((id) => (
        <td key={id} className={id === 'position' ? 'max-w-[220px]' : undefined}>{cells[id]}</td>
      ))}
    </tr>
  );
}

function TagList({ tags }: { tags: string[] }) {
  if (tags.length === 0) return <span className="text-faint">—</span>;
  return (
    <span className="flex items-center gap-1">
      {tags.slice(0, MAX_TAGS_SHOWN).map((t) => (
        <Tag key={t} color="gray">{t}</Tag>
      ))}
      {tags.length > MAX_TAGS_SHOWN && <span className="text-xs text-faint">+{tags.length - MAX_TAGS_SHOWN}</span>}
    </span>
  );
}

function GroupList({ ids, groupsById }: { ids: string[]; groupsById: Map<string, Group> }) {
  const groups = ids.map((id) => groupsById.get(id)).filter((g): g is Group => Boolean(g));
  if (groups.length === 0) return <span className="text-faint">—</span>;
  return (
    <span className="flex items-center gap-1">
      {groups.slice(0, MAX_TAGS_SHOWN).map((g) => (
        <Tag key={g.id} color="blue">{g.emoji} {g.name}</Tag>
      ))}
      {groups.length > MAX_TAGS_SHOWN && <span className="text-xs text-faint">+{groups.length - MAX_TAGS_SHOWN}</span>}
    </span>
  );
}

function SocialIcons({ contact }: { contact: Contact }) {
  const items = Object.entries(SOCIAL_ICONS).filter(([key]) => contact.social?.[key as keyof Contact['social']]);
  if (items.length === 0) return <span className="text-faint">—</span>;
  return (
    <span className="flex items-center gap-1.5">
      {items.map(([key, { icon: Icon, label }]) => {
        const href = socialHref(key, contact.social[key as keyof Contact['social']]);
        const icon = <Icon className="size-4" aria-hidden />;
        return href ? (
          <a key={key} href={href} target="_blank" rel="noopener noreferrer" aria-label={label} title={label} className="text-muted hover:text-fg">
            {icon}
          </a>
        ) : (
          <span key={key} title={label} className="text-muted">{icon}</span>
        );
      })}
    </span>
  );
}
