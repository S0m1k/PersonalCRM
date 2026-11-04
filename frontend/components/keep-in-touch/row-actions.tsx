'use client';

import { useState } from 'react';
import Link from 'next/link';
import { BellOff, Check, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { markTouched, snoozeContact, type InteractionKind } from '@/lib/api-crm';
import { SNOOZE_OPTIONS, type KitRow } from '@/lib/keep-in-touch';
import { cn, errorText, plural } from '@/lib/utils';
import { INTERACTION_KINDS, INTERACTION_KIND_ORDER, revalidateInteractions } from '@/components/interactions';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Menu, MenuContent, MenuItem, MenuTrigger, Popover, PopoverContent, PopoverTrigger, Tooltip } from '@/components/ui/overlays';

/** «Связался»: тип + необязательная заметка → markTouched. */
export function TouchedButton({ row, iconOnly = false }: { row: KitRow; iconOnly?: boolean }) {
  const [isOpen, setIsOpen] = useState(false);
  const [kind, setKind] = useState<InteractionKind>('message');
  const [note, setNote] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  async function save() {
    setIsSaving(true);
    try {
      await markTouched(row.id, { kind, body: note.trim() });
      await revalidateInteractions();
      toast.success(`Отмечено: связались с ${row.name}`);
      setIsOpen(false);
      setNote('');
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size={iconOnly ? 'icon' : 'sm'} className={iconOnly ? 'size-7' : undefined} aria-label={`Связался: ${row.name}`}>
          <Check /> {!iconOnly && 'Связался'}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 space-y-3 p-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Как связались">
          {INTERACTION_KIND_ORDER.map((k) => {
            const { icon: Icon, label } = INTERACTION_KINDS[k];
            return (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={kind === k}
                onClick={() => setKind(k)}
                className={cn(
                  'inline-flex h-7 items-center gap-1 rounded-full border px-2.5 text-xs [&_svg]:size-3.5',
                  kind === k ? 'border-accent-300 bg-accent-50 text-accent-700 dark:border-accent-700 dark:bg-accent-950 dark:text-accent-200' : 'border-line text-muted hover:bg-hover',
                )}
              >
                <Icon aria-hidden /> {label}
              </button>
            );
          })}
        </div>
        <Input
          autoFocus
          value={note}
          maxLength={500}
          placeholder="Заметка (необязательно)"
          aria-label="Заметка"
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !isSaving && void save()}
        />
        <Button variant="primary" size="sm" className="w-full" disabled={isSaving} onClick={() => void save()}>
          {isSaving ? 'Записываю…' : 'Записать'}
        </Button>
      </PopoverContent>
    </Popover>
  );
}

/** «Отложить» на 1/3/7/14/30 дней. */
export function SnoozeMenu({ row, iconOnly = false }: { row: KitRow; iconOnly?: boolean }) {
  async function snooze(days: number) {
    try {
      await snoozeContact(row.id, days);
      await revalidateInteractions();
      toast.success(`Напомню через ${days} ${plural(days, 'день', 'дня', 'дней')}`);
    } catch (err) {
      toast.error(errorText(err));
    }
  }
  return (
    <Menu>
      <MenuTrigger asChild>
        <Button variant="ghost" size={iconOnly ? 'icon' : 'sm'} className={iconOnly ? 'size-7' : undefined} aria-label={`Отложить: ${row.name}`}>
          <BellOff /> {!iconOnly && 'Отложить'}
        </Button>
      </MenuTrigger>
      <MenuContent align="end">
        {SNOOZE_OPTIONS.map((d) => (
          <MenuItem key={d} onSelect={() => void snooze(d)}>
            На {d} {plural(d, 'день', 'дня', 'дней')}
          </MenuItem>
        ))}
      </MenuContent>
    </Menu>
  );
}

export function OpenCardLink({ row }: { row: KitRow }) {
  return (
    <Tooltip label="Открыть карточку" side="top">
      <Button asChild variant="ghost" size="icon" className="size-7">
        <Link href={`/contacts/${row.id}`} aria-label={`Открыть карточку: ${row.name}`}>
          <ExternalLink />
        </Link>
      </Button>
    </Tooltip>
  );
}

/** Набор быстрых действий строки списка / «Ближайших». */
export function RowActions({ row }: { row: KitRow }) {
  return (
    <div className="flex items-center justify-end gap-1">
      <TouchedButton row={row} />
      <SnoozeMenu row={row} />
      <OpenCardLink row={row} />
    </div>
  );
}
