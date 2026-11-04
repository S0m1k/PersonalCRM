'use client';

import { useState, type FormEvent } from 'react';
import { BellOff, Check, Flag, Repeat } from 'lucide-react';
import { toast } from 'sonner';
import type { Contact, ContactUpdate } from '@/lib/api';
import { snoozeContact } from '@/lib/api-crm';
import { FREQUENCY_PRESETS, frequencyLabel } from '@/lib/frequency';
import { PRIORITY_LEVELS, PRIORITY_META, isPriorityLevel, priorityLabel } from '@/lib/priority';
import { cn, errorText, formatDate } from '@/lib/utils';
import { Pill } from '@/components/ui/pill';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';
import { Tag } from '@/components/ui/tag';

const optionClass = 'flex h-8 w-full items-center justify-between gap-2 rounded-lg px-2 text-left text-sm hover:bg-hover';
const SNOOZE_DAYS = [7, 30, 90] as const;
const MAX_FREQUENCY_DAYS = 730;

type Props = {
  contact: Contact;
  onSave: (patch: ContactUpdate) => void;
  onRefresh: () => void;
};

export function PriorityPill({ contact, onSave }: Pick<Props, 'contact' | 'onSave'>) {
  const [isOpen, setIsOpen] = useState(false);
  const current = isPriorityLevel(contact.priority) ? contact.priority : null;
  const isSet = Boolean(contact.priority) && contact.priority !== 'none';

  function choose(level: string) {
    setIsOpen(false);
    const next = level === 'none' ? '' : level;
    if (next !== contact.priority) onSave({ priority: next });
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Pill icon={Flag} isActive={isSet} aria-label="Приоритет">
          {isSet ? priorityLabel(contact.priority) : 'Приоритет'}
        </Pill>
      </PopoverTrigger>
      <PopoverContent className="w-52">
        {PRIORITY_LEVELS.map((level) => (
          <button key={level} type="button" onClick={() => choose(level)} className={optionClass}>
            <Tag color={PRIORITY_META[level].color}>{PRIORITY_META[level].label}</Tag>
            {(current === level || (level === 'none' && !contact.priority)) && <Check className="size-4 text-muted" />}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  );
}

export function FrequencyPill({ contact, onSave, onRefresh }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [custom, setCustom] = useState('');
  const days = contact.keep_in_touch.frequency_days;
  const snoozedUntil = contact.keep_in_touch.snoozed_until;

  function setFrequency(value: number | null) {
    setIsOpen(false);
    if (value !== days) onSave({ keep_in_touch: { ...contact.keep_in_touch, frequency_days: value } });
  }

  function submitCustom(e: FormEvent) {
    e.preventDefault();
    const n = Number(custom);
    if (!Number.isInteger(n) || n < 1 || n > MAX_FREQUENCY_DAYS) {
      toast.error(`Укажите число дней от 1 до ${MAX_FREQUENCY_DAYS}`);
      return;
    }
    setCustom('');
    setFrequency(n);
  }

  async function snooze(count: number) {
    setIsOpen(false);
    try {
      await snoozeContact(contact.id, count);
      toast.success(`Напоминание отложено на ${count} дн.`);
      onRefresh();
    } catch (err) {
      toast.error(errorText(err));
    }
  }

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <Pill icon={Repeat} isActive={Boolean(days)} aria-label="Частота общения">
          {days ? frequencyLabel(days) : 'Частота'}
        </Pill>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        {FREQUENCY_PRESETS.map((preset) => (
          <button key={preset.days} type="button" onClick={() => setFrequency(preset.days)} className={optionClass}>
            {preset.label}
            {days === preset.days && <Check className="size-4 text-muted" />}
          </button>
        ))}
        <form onSubmit={submitCustom} className="mt-1 flex items-center gap-1.5 border-t border-line px-2 pt-2">
          <input
            type="number"
            min={1}
            max={MAX_FREQUENCY_DAYS}
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Своё, дней"
            aria-label="Своя частота в днях"
            className="h-8 min-w-0 flex-1 rounded-lg border border-line bg-surface px-2 text-sm outline-none focus:border-accent"
          />
          <button type="submit" className="h-8 rounded-lg px-2 text-sm font-medium text-accent hover:bg-hover">
            Задать
          </button>
        </form>
        {days && (
          <button type="button" onClick={() => setFrequency(null)} className={cn(optionClass, 'mt-1 text-muted')}>
            Не напоминать
          </button>
        )}
        <div className="mt-1 border-t border-line px-2 pb-1 pt-2">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs text-muted">
            <BellOff className="size-3.5" /> Отложить
            {snoozedUntil && <span className="text-faint">· до {formatDate(snoozedUntil)}</span>}
          </div>
          <div className="flex gap-1">
            {SNOOZE_DAYS.map((count) => (
              <button
                key={count}
                type="button"
                onClick={() => void snooze(count)}
                className="h-7 flex-1 rounded-lg border border-line text-[13px] hover:bg-hover"
              >
                {count} дн.
              </button>
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
