'use client';

/**
 * Создание и правка встречи: время, люди (привязка к контактам), место, описание,
 * в какой календарь записать и дописывать ли туда открытые вопросы к участникам.
 */

import { useState, type FormEvent } from 'react';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { CircleHelp, ExternalLink, Loader2, Trash2, Upload } from 'lucide-react';
import {
  createEvent,
  deleteEvent,
  pushEvent,
  updateEvent,
  type CalendarConnection,
  type CalendarEvent,
  type EventInput,
} from '@/lib/api';
import { addDays, browserTimeZone, eventBounds, nextHour, toDateInput, toDateTimeInput } from '@/lib/calendar';
import { errorText, safeUrl } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input, Textarea } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';
import { ContactPicker, type PickedContact } from './contact-picker';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null — новая встреча */
  event: CalendarEvent | null;
  /** Для новой встречи: день и люди по умолчанию */
  initialDay?: Date;
  initialContacts?: PickedContact[];
};

const PROVIDER_NAMES: Record<string, string> = { microsoft: 'Outlook', google: 'Google' };
const HOUR_MS = 3_600_000;

type Form = {
  title: string;
  allDay: boolean;
  start: string;
  end: string;
  location: string;
  description: string;
  contacts: PickedContact[];
  pushQuestions: boolean;
  connectionId: string;
};

function initialForm(event: CalendarEvent | null, day?: Date, contacts: PickedContact[] = []): Form {
  if (event) {
    const { start, end } = eventBounds(event);
    return {
      title: event.title,
      allDay: event.all_day,
      // В форме «весь день» — последний день включительно
      start: event.all_day ? toDateInput(start) : toDateTimeInput(start),
      end: event.all_day ? toDateInput(addDays(end, -1)) : toDateTimeInput(end),
      location: event.location,
      description: event.description,
      contacts: event.contacts,
      pushQuestions: event.push_questions,
      connectionId: '',
    };
  }
  const start = nextHour(day);
  return {
    title: '',
    allDay: false,
    start: toDateTimeInput(start),
    end: toDateTimeInput(new Date(start.getTime() + HOUR_MS)),
    location: '',
    description: '',
    contacts,
    pushQuestions: false,
    connectionId: '',
  };
}

function toPayload(form: Form): EventInput {
  const lastDay = form.end || form.start;
  return {
    title: form.title.trim(),
    all_day: form.allDay,
    start: form.start,
    // Бэкенду для «весь день» нужен день ПОСЛЕ последнего
    end: form.allDay ? toDateInput(addDays(new Date(`${lastDay}T00:00`), 1)) : form.end || undefined,
    timezone: browserTimeZone(),
    location: form.location.trim(),
    description: form.description,
    contact_ids: form.contacts.map((c) => c.id),
    push_questions: form.pushQuestions,
  };
}

export function EventDialog({ open, onOpenChange, event, initialDay, initialContacts }: Props) {
  const sourceNote =
    event && event.source !== 'crm' ? `Из ${PROVIDER_NAMES[event.source]} — правки уйдут и туда.` : undefined;
  // Форма монтируется заново при каждом открытии — состояние берётся из актуального события
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={event ? 'Встреча' : 'Новая встреча'} description={sourceNote} className="top-[8vh] max-w-lg">
        <EventForm event={event} initialDay={initialDay} initialContacts={initialContacts} onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

type FormProps = Omit<Props, 'open' | 'onOpenChange'> & { onDone: () => void };

function EventForm({ event, initialDay, initialContacts, onDone }: FormProps) {
  const { mutate } = useSWRConfig();
  const { data: connections = [] } = useSWR<CalendarConnection[]>('/api/sync/connections');
  const [form, setForm] = useState<Form>(() => initialForm(event, initialDay, initialContacts));
  const [isSaving, setIsSaving] = useState(false);

  const writable = connections.filter((c) => c.calendar_access && PROVIDER_NAMES[c.provider]);
  const isRemote = !!event && event.source !== 'crm';
  const canPush = isRemote || form.connectionId !== '';
  const link = event?.web_link ? safeUrl(event.web_link) : undefined;

  function set<K extends keyof Form>(key: K, value: Form[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function refresh() {
    void mutate((k) => typeof k === 'string' && k.startsWith('/api/calendar'));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form.title.trim()) return;
    setIsSaving(true);
    try {
      const payload = toPayload(form);
      if (event) {
        await updateEvent(event.id, payload);
        if (!isRemote && form.connectionId) await pushEvent(event.id, form.connectionId);
      } else {
        await createEvent({ ...payload, connection_id: form.connectionId || null });
      }
      toast.success(event ? 'Сохранено' : 'Встреча создана');
      refresh();
      onDone();
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDelete() {
    if (!event) return;
    const where = isRemote ? ` и из ${PROVIDER_NAMES[event.source]}` : '';
    if (!window.confirm(`Удалить «${event.title}» из CRM${where}?`)) return;
    try {
      await deleteEvent(event.id);
      toast.success('Удалено');
      refresh();
      onDone();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex max-h-[72vh] flex-col gap-4 overflow-y-auto px-0.5 pb-0.5">
      <Input
        autoFocus={!event}
        placeholder="Что за встреча"
        value={form.title}
        onChange={(e) => set('title', e.target.value)}
        maxLength={300}
        aria-label="Название"
      />

      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-2 gap-2">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Начало
            <Input
              type={form.allDay ? 'date' : 'datetime-local'}
              value={form.start}
              onChange={(e) => set('start', e.target.value)}
              required
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted">
            {form.allDay ? 'Последний день' : 'Конец'}
            <Input
              type={form.allDay ? 'date' : 'datetime-local'}
              value={form.end}
              min={form.start}
              onChange={(e) => set('end', e.target.value)}
            />
          </label>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.allDay}
            onChange={(e) => {
              const allDay = e.target.checked;
              setForm((prev) => ({
                ...prev,
                allDay,
                start: allDay ? prev.start.slice(0, 10) : `${prev.start.slice(0, 10)}T09:00`,
                end: allDay ? prev.end.slice(0, 10) : `${(prev.end || prev.start).slice(0, 10)}T10:00`,
              }));
            }}
            className="size-4 accent-[rgb(var(--accent))]"
          />
          Весь день
        </label>
      </div>

      <div>
        <div className="mb-1.5 text-xs font-medium text-muted">Люди</div>
        <ContactPicker value={form.contacts} onChange={(contacts) => set('contacts', contacts)} />
      </div>

      {event && event.questions.length > 0 && (
        <div className="rounded-md bg-tag-blue/50 px-3 py-2">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted">
            <CircleHelp className="size-3.5" /> Хотел спросить на встрече
          </div>
          <ul className="flex flex-col gap-0.5 text-sm">
            {event.questions.map((q) => (
              <li key={q.id}>
                {q.text} <span className="text-xs text-muted">— {q.contact_name}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <Input
        placeholder="Место или ссылка"
        value={form.location}
        onChange={(e) => set('location', e.target.value)}
        maxLength={500}
        aria-label="Место"
      />
      <Textarea
        placeholder="Описание"
        value={form.description}
        onChange={(e) => set('description', e.target.value)}
        aria-label="Описание"
      />

      {!isRemote && writable.length > 0 && (
        <label className="flex flex-col gap-1 text-xs text-muted">
          Записать в календарь
          <select
            value={form.connectionId}
            onChange={(e) => set('connectionId', e.target.value)}
            className="h-8 rounded border border-line bg-surface px-2 text-sm text-fg"
          >
            <option value="">Только в CRM</option>
            {writable.map((c) => (
              <option key={c.id} value={c.id}>
                {PROVIDER_NAMES[c.provider]}
              </option>
            ))}
          </select>
        </label>
      )}
      {canPush && (
        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.pushQuestions}
            onChange={(e) => set('pushQuestions', e.target.checked)}
            className="mt-0.5 size-4 accent-[rgb(var(--accent))]"
          />
          <span>
            Дописать открытые вопросы к участникам в описание
            <span className="block text-xs text-muted">Их увидят все, кто видит событие в календаре.</span>
          </span>
        </label>
      )}

      <div className="mt-1 flex items-center gap-2">
        {event && (
          <Button type="button" variant="danger" onClick={() => void handleDelete()}>
            <Trash2 /> Удалить
          </Button>
        )}
        {link && (
          <Button asChild variant="ghost">
            <a href={link} target="_blank" rel="noopener noreferrer">
              <ExternalLink /> Открыть в {PROVIDER_NAMES[event?.source ?? ''] ?? 'календаре'}
            </a>
          </Button>
        )}
        <div className="flex-1" />
        <Button type="submit" variant="primary" disabled={isSaving || !form.title.trim()}>
          {isSaving ? <Loader2 className="animate-spin" /> : form.connectionId ? <Upload /> : null}
          {event ? 'Сохранить' : 'Создать'}
        </Button>
      </div>
    </form>
  );
}
