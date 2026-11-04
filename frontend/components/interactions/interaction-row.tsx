'use client';

import { useState } from 'react';
import { CalendarDays, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { deleteInteraction, type Interaction } from '@/lib/api-crm';
import { cn, errorText } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/overlays';
import { ContactChip } from './contact-chip';
import { whenLabel } from './format';
import { InteractionComposer } from './interaction-composer';
import { InteractionKindIcon, kindLabel } from './kinds';
import { revalidateInteractions } from './revalidate';

export interface InteractionRowProps {
  interaction: Interaction;
  /** Показывать плашки людей (в Timeline карточки контакта они лишние). */
  showContacts?: boolean;
  className?: string;
}

/** Заголовок записи: title, иначе первая строка текста, иначе название типа. */
export function interactionTitle(item: Interaction): string {
  if (item.title.trim()) return item.title.trim();
  const firstLine = item.body.split('\n').find((l) => l.trim());
  return firstLine?.trim() || kindLabel(item.kind);
}

/**
 * Строка ленты: иконка типа, заголовок, люди, дата. Клик раскрывает текст; у обычных записей есть меню
 * «Изменить / Удалить» (сама показывает диалог правки и обновляет кэш), встречи из календаря — только чтение.
 */
export function InteractionRow({ interaction, showContacts = true, className }: InteractionRowProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const isCalendar = interaction.source === 'calendar';
  const title = interactionTitle(interaction);
  const hasBody = interaction.body.trim() !== '' && interaction.body.trim() !== title;

  async function remove() {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await deleteInteraction(interaction.id);
      await revalidateInteractions();
      toast.success('Запись удалена');
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <li className={cn('group rounded-xl hover:bg-hover/60', className)}>
      <div className="flex items-start gap-3 px-2 py-2.5">
        <InteractionKindIcon kind={interaction.kind} className="mt-0.5" />
        <button
          type="button"
          aria-expanded={isOpen}
          disabled={!hasBody && !showContacts}
          onClick={() => setIsOpen((v) => !v)}
          className="min-w-0 flex-1 text-left"
        >
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-medium">{title}</span>
            {isCalendar && (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-crm-meeting/15 px-1.5 py-0.5 text-[11px] font-medium text-crm-meeting">
                <CalendarDays className="size-3" aria-hidden /> Календарь
              </span>
            )}
          </span>
          {showContacts && interaction.contact_ids.length > 0 && (
            <span className="mt-1 flex flex-wrap gap-1">
              {interaction.contact_ids.map((id) => (
                <ContactChip key={id} id={id} />
              ))}
            </span>
          )}
        </button>
        <time dateTime={interaction.occurred_at} className="shrink-0 pt-1 text-xs text-muted">
          {whenLabel(interaction.occurred_at)}
        </time>
        {!interaction.read_only ? (
          <Menu>
            <MenuTrigger asChild>
              <Button variant="ghost" size="icon" className="-my-1 size-7 opacity-0 focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100" aria-label="Действия с записью">
                <MoreHorizontal />
              </Button>
            </MenuTrigger>
            <MenuContent align="end">
              <MenuItem onSelect={() => setIsEditing(true)}>
                <Pencil /> Изменить
              </MenuItem>
              <MenuItem danger onSelect={() => void remove()}>
                <Trash2 /> Удалить
              </MenuItem>
            </MenuContent>
          </Menu>
        ) : (
          <span className="size-7 shrink-0" aria-hidden />
        )}
      </div>
      {isOpen && (
        <div className="pb-3 pl-14 pr-10 text-sm text-fg/90">
          {hasBody ? <p className="whitespace-pre-wrap">{interaction.body}</p> : <p className="text-faint">Без текста</p>}
        </div>
      )}
      {isEditing && <InteractionComposer open onOpenChange={setIsEditing} interaction={interaction} />}
    </li>
  );
}
