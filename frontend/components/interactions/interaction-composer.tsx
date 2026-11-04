'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import { createInteraction, updateInteraction, type Interaction, type InteractionKind } from '@/lib/api-crm';
import { errorText } from '@/lib/utils';
import { ContactPicker, type PickedContact } from '@/components/calendar/contact-picker';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { SectionLabel } from '@/components/ui/section-label';
import { cn } from '@/lib/utils';
import { toLocalInput } from './format';
import { INTERACTION_KINDS, INTERACTION_KIND_ORDER } from './kinds';
import { revalidateInteractions } from './revalidate';
import { useContactsByIds } from './use-contacts-by-ids';

export interface InteractionComposerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Передан — режим правки, иначе создание. */
  interaction?: Interaction;
  /** Люди, выбранные заранее при создании (например, текущая карточка). */
  defaultContacts?: PickedContact[];
  defaultKind?: InteractionKind;
  onSaved?: (saved: Interaction) => void;
}

/** Диалог «Добавить заметку» / «Изменить запись». Сам обновляет кэш лент и Keep in touch после сохранения. */
export function InteractionComposer({ open, onOpenChange, ...rest }: InteractionComposerProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={rest.interaction ? 'Изменить запись' : 'Добавить заметку'}
        description="Что было, с кем и когда — чтобы помнить, на чём остановились."
        className="max-w-lg"
      >
        {/* Форма монтируется заново при каждом открытии — состояние не протекает между записями */}
        <ComposerForm onClose={() => onOpenChange(false)} {...rest} />
      </DialogContent>
    </Dialog>
  );
}

function ComposerForm({
  interaction,
  defaultContacts = [],
  defaultKind = 'note',
  onSaved,
  onClose,
}: Omit<InteractionComposerProps, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const loaded = useContactsByIds(interaction?.contact_ids ?? []);
  const [picked, setPicked] = useState<PickedContact[] | null>(interaction ? null : defaultContacts);
  const contacts = picked ?? loaded;
  const [kind, setKind] = useState<InteractionKind>(interaction?.kind ?? defaultKind);
  const [title, setTitle] = useState(interaction?.title ?? '');
  const [body, setBody] = useState(interaction?.body ?? '');
  const [when, setWhen] = useState(toLocalInput(interaction ? new Date(interaction.occurred_at) : new Date()));
  const [isSaving, setIsSaving] = useState(false);

  const canSave = contacts.length > 0 && when !== '' && !isSaving;

  async function save() {
    setIsSaving(true);
    try {
      const payload = {
        contact_ids: contacts.map((c) => c.id),
        kind,
        title: title.trim(),
        body: body.trim(),
        occurred_at: new Date(when).toISOString(),
      };
      const saved = interaction ? await updateInteraction(interaction.id, payload) : await createInteraction(payload);
      await revalidateInteractions();
      toast.success(interaction ? 'Запись обновлена' : 'Заметка добавлена');
      onSaved?.(saved);
      onClose();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSave) void save();
      }}
    >
      <div className="space-y-1.5">
        <SectionLabel>С кем</SectionLabel>
        <ContactPicker value={contacts} onChange={setPicked} />
      </div>

      <div className="space-y-1.5">
        <SectionLabel>Тип</SectionLabel>
        <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Тип записи">
          {INTERACTION_KIND_ORDER.map((k) => {
            const { icon: Icon, label } = INTERACTION_KINDS[k];
            const isOn = kind === k;
            return (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={isOn}
                onClick={() => setKind(k)}
                className={cn(
                  'inline-flex h-7 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors [&_svg]:size-3.5',
                  isOn ? 'border-accent-300 bg-accent-50 text-accent-700 dark:border-accent-700 dark:bg-accent-950 dark:text-accent-200' : 'border-line text-muted hover:bg-hover hover:text-fg',
                )}
              >
                <Icon aria-hidden />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="space-y-1.5">
        <SectionLabel>Заголовок</SectionLabel>
        <Input value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} placeholder="Например, «Кофе у офиса»" />
      </div>

      <div className="space-y-1.5">
        <SectionLabel>Заметка</SectionLabel>
        <Textarea value={body} rows={4} onChange={(e) => setBody(e.target.value)} placeholder="О чём говорили, о чём договорились…" />
      </div>

      <div className="space-y-1.5">
        <SectionLabel>Когда</SectionLabel>
        <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className="w-auto" />
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="ghost" onClick={onClose}>
          Отмена
        </Button>
        <Button type="submit" variant="primary" disabled={!canSave}>
          {isSaving ? 'Сохраняю…' : 'Сохранить'}
        </Button>
      </div>
      {contacts.length === 0 && <p className="text-xs text-faint">Выберите хотя бы одного человека.</p>}
    </form>
  );
}
