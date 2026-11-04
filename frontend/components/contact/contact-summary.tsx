'use client';

import type { ReactNode } from 'react';
import { Sparkles } from 'lucide-react';
import type { Contact, ContactUpdate } from '@/lib/api';
import { frequencyLabel } from '@/lib/frequency';
import { formatDate, relativeTime } from '@/lib/utils';
import { EditableText } from '@/components/contact/editable';
import { SectionLabel } from '@/components/ui/section-label';

const TEASER_LINES = 2;

function Block({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="mt-6">
      <SectionLabel className="mb-1.5 block">{label}</SectionLabel>
      {children}
    </section>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <SectionLabel className="mb-1.5 block">{label}</SectionLabel>
      <div className="min-h-8 text-sm">{children}</div>
    </div>
  );
}

type Props = {
  contact: Contact;
  dossierText: string | null;
  onSave: (patch: ContactUpdate) => void;
  onOpenDossier: () => void;
};

export function ContactSummary({ contact, dossierText, onSave, onOpenDossier }: Props) {
  const teaser = dossierText
    ?.split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .slice(0, TEASER_LINES)
    .join('\n');
  const days = contact.keep_in_touch.frequency_days;

  return (
    <>
      <Block label="Описание">
        <EditableText
          isMultiline
          value={contact.description}
          onCommit={(v) => onSave({ description: v })}
          placeholder="Добавить описание…"
          ariaLabel="Описание"
          className="-mx-2 text-[15px]"
        />
      </Block>

      {teaser && (
        <Block label="Досье ИИ">
          <p className="line-clamp-2 whitespace-pre-line text-[15px] text-muted">{teaser}</p>
          <button
            type="button"
            onClick={onOpenDossier}
            className="mt-1 inline-flex items-center gap-1 text-sm font-medium text-accent hover:text-accent-hover"
          >
            <Sparkles className="size-3.5" /> Открыть досье
          </button>
        </Block>
      )}

      <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 border-y border-line py-4 lg:grid-cols-4">
        <Stat label="Добавлен">{formatDate(contact.created_at.slice(0, 10))}</Stat>
        <Stat label="Первая встреча">
          <EditableText
            type="date"
            value={contact.first_met_at ?? ''}
            display={formatDate(contact.first_met_at)}
            onCommit={(v) => onSave({ first_met_at: v || null })}
            placeholder="Указать дату"
            ariaLabel="Дата первой встречи"
            className="-mx-2"
          />
          <EditableText
            value={contact.first_met_note}
            onCommit={(v) => onSave({ first_met_note: v })}
            placeholder="Где познакомились…"
            ariaLabel="Заметка о первой встрече"
            className="-mx-2 text-muted"
          />
        </Stat>
        <Stat label="Последнее взаимодействие">
          {contact.last_interaction_at ? relativeTime(contact.last_interaction_at) : <span className="text-faint">Пока нет</span>}
        </Stat>
        <Stat label="Частота">{days ? frequencyLabel(days) : <span className="text-faint">Не задана</span>}</Stat>
      </div>
    </>
  );
}
