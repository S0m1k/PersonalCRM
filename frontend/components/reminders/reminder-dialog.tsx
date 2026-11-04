'use client';

import { useState, type FormEvent } from 'react';
import { toast } from 'sonner';
import {
  createReminder,
  localISODate,
  REPEAT_LABELS,
  updateReminder,
  type Reminder,
  type ReminderInput,
  type ReminderRepeat,
} from '@/lib/api-reminders';
import { errorText } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { ContactPicker, type PickedContact } from '@/components/calendar/contact-picker';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null — новое напоминание */
  reminder: Reminder | null;
  initialContact?: PickedContact;
  onSaved: () => void;
};

type Form = Omit<ReminderInput, 'contact_id' | 'due_time'> & { contact: PickedContact | null; due_time: string };

function initialForm(reminder: Reminder | null, contact?: PickedContact): Form {
  if (reminder) {
    return {
      title: reminder.title,
      note: reminder.note,
      due_date: reminder.due_date,
      due_time: reminder.due_time ?? '',
      repeat: reminder.repeat,
      contact: reminder.contact_id ? { id: reminder.contact_id, name: reminder.contact_name } : null,
    };
  }
  return { title: '', note: '', due_date: localISODate(), due_time: '', repeat: 'none', contact: contact ?? null };
}

const labelClass = 'mb-1 block text-xs font-medium text-muted';

export function ReminderDialog({ open, onOpenChange, reminder, initialContact, onSaved }: Props) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={reminder ? 'Изменить напоминание' : 'Новое напоминание'}>
        {/* key: форма пересоздаётся при каждом открытии */}
        <ReminderForm
          key={reminder?.id ?? 'new'}
          reminder={reminder}
          initialContact={initialContact}
          onClose={() => onOpenChange(false)}
          onSaved={onSaved}
        />
      </DialogContent>
    </Dialog>
  );
}

function ReminderForm({
  reminder,
  initialContact,
  onClose,
  onSaved,
}: Pick<Props, 'reminder' | 'initialContact' | 'onSaved'> & { onClose: () => void }) {
  const [form, setForm] = useState<Form>(() => initialForm(reminder, initialContact));
  const [isSaving, setIsSaving] = useState(false);

  function patch(changes: Partial<Form>) {
    setForm((prev) => ({ ...prev, ...changes }));
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const title = form.title.trim();
    if (!title || !form.due_date) return;
    const payload: ReminderInput = {
      title,
      note: form.note.trim(),
      due_date: form.due_date,
      due_time: form.due_time || null,
      repeat: form.repeat,
      contact_id: form.contact?.id ?? null,
    };
    setIsSaving(true);
    try {
      if (reminder) await updateReminder(reminder.id, payload);
      else await createReminder(payload);
      onSaved();
      onClose();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <div>
        <label htmlFor="reminder-title" className={labelClass}>
          Что напомнить
        </label>
        <Input
          id="reminder-title"
          autoFocus
          required
          maxLength={300}
          placeholder="Например, поздравить с запуском"
          value={form.title}
          onChange={(e) => patch({ title: e.target.value })}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="reminder-date" className={labelClass}>
            Дата
          </label>
          <Input id="reminder-date" type="date" required value={form.due_date} onChange={(e) => patch({ due_date: e.target.value })} />
        </div>
        <div>
          <label htmlFor="reminder-time" className={labelClass}>
            Время (необязательно)
          </label>
          <Input id="reminder-time" type="time" value={form.due_time} onChange={(e) => patch({ due_time: e.target.value })} />
        </div>
      </div>
      <div>
        <label htmlFor="reminder-repeat" className={labelClass}>
          Повтор
        </label>
        <select
          id="reminder-repeat"
          value={form.repeat}
          onChange={(e) => patch({ repeat: e.target.value as ReminderRepeat })}
          className="h-9 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm shadow-xs focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20"
        >
          {(Object.keys(REPEAT_LABELS) as ReminderRepeat[]).map((value) => (
            <option key={value} value={value}>
              {REPEAT_LABELS[value]}
            </option>
          ))}
        </select>
      </div>
      <div>
        <span className={labelClass}>Человек</span>
        <ContactPicker value={form.contact ? [form.contact] : []} onChange={(list) => patch({ contact: list.at(-1) ?? null })} />
      </div>
      <div>
        <label htmlFor="reminder-note" className={labelClass}>
          Заметка
        </label>
        <Textarea id="reminder-note" rows={2} maxLength={2000} value={form.note} onChange={(e) => patch({ note: e.target.value })} />
      </div>
      <div className="mt-1 flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onClose}>
          Отмена
        </Button>
        <Button type="submit" variant="primary" disabled={isSaving || !form.title.trim()}>
          {reminder ? 'Сохранить' : 'Добавить'}
        </Button>
      </div>
    </form>
  );
}
