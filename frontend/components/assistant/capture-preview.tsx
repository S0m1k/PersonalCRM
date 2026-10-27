'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AtSign, Check, CircleCheck, CircleHelp, NotebookPen, PenLine, Phone, UserPlus } from 'lucide-react';
import type { ApplyResult, CaptureAction, CaptureResult } from '@/lib/api';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

const NEW_CONTACT = '__new__';

function ActionBody({ action }: { action: CaptureAction }) {
  switch (action.type) {
    case 'update_field':
      return (
        <>
          <span className="text-muted">{action.label}: </span>
          {action.old && <span className="text-faint line-through">{action.old}</span>}
          {action.old && <span className="text-faint"> → </span>}
          <span className="font-medium">{action.new}</span>
        </>
      );
    case 'answer_question':
      return (
        <>
          <span className="text-muted">{action.question} </span>
          <span className="font-medium">{action.answer}</span>
          {!action.question_id && <span className="text-faint"> · новый закрытый вопрос</span>}
        </>
      );
    case 'add_question':
      return <span>{action.text}</span>;
    case 'add_note':
      return <span>{action.text}</span>;
    case 'add_phone':
    case 'add_email':
      return <span className="font-medium">{action.value}</span>;
    case 'create_contact':
      return (
        <>
          <span className="text-muted">Создать контакт </span>
          <span className="font-medium">{action.name}</span>
        </>
      );
  }
}

const ACTION_META: Record<CaptureAction['type'], { icon: typeof PenLine; label: string }> = {
  update_field: { icon: PenLine, label: 'Поле' },
  answer_question: { icon: CircleCheck, label: 'Ответ' },
  add_question: { icon: CircleHelp, label: 'Спросить' },
  add_note: { icon: NotebookPen, label: 'Заметка' },
  add_phone: { icon: Phone, label: 'Телефон' },
  add_email: { icon: AtSign, label: 'Почта' },
  create_contact: { icon: UserPlus, label: 'Контакт' },
};

type Props = {
  result: CaptureResult;
  applied: ApplyResult | null;
  busy: boolean;
  onApply: (actions: number[], contactId: string | null, newName?: string) => void;
  onDiscard: () => void;
};

/** Предпросмотр быстрого захвата: что изменится, у кого — и применить выбранное. */
export function CapturePreview({ result, applied, busy, onApply, onDiscard }: Props) {
  const valid = result.actions.filter((a) => !a.error);
  const [selected, setSelected] = useState<Set<number>>(() => new Set(valid.map((a) => a.index)));
  const [target, setTarget] = useState<string>(result.contact_id ?? (result.candidates.length ? '' : NEW_CONTACT));
  const foundName = [result.new_contact?.first_name, result.new_contact?.last_name].filter(Boolean).join(' ');
  // Имя нового контакта правится прямо здесь: модель может не найти его в записи или ошибиться
  const [typedName, setTypedName] = useState(foundName);
  const isNew = target === NEW_CONTACT;
  const newName = typedName.trim();

  function toggle(index: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  if (result.actions.length === 0) {
    return <p className="text-sm text-muted">Не нашёл в записи, что сохранить. Попробуйте написать подробнее.</p>;
  }

  if (applied) {
    const failed = applied.results.filter((r) => !r.ok);
    return (
      <div className="rounded-md border border-line bg-surface px-4 py-3 text-sm">
        <div className="flex items-center gap-2 font-medium">
          <Check className="size-4 text-accent" />
          Сохранено: {applied.results.length - failed.length} из {applied.results.length}
        </div>
        {failed.map((r) => (
          <div key={r.index} className="mt-1 text-danger">
            Пункт {r.index + 1}: {r.error}
          </div>
        ))}
        <Link href={`/contacts/${applied.contact_id}`} className="mt-2 inline-block text-accent hover:underline">
          Открыть карточку{applied.created_contact ? ` (новый контакт ${applied.created_contact.name})` : ''}
        </Link>
      </div>
    );
  }

  const canApply = selected.size > 0 && target !== '' && (!isNew || newName !== '') && !busy;

  return (
    <div className="flex flex-col gap-4">
      <fieldset>
        <legend className="mb-1.5 text-sm font-semibold text-muted">Кому</legend>
        <div className="flex flex-wrap gap-1.5">
          {result.candidates.map((c) => (
            <TargetChip key={c.id} active={target === c.id} onClick={() => setTarget(c.id)}>
              {c.name}
              {(c.company || c.city) && <span className="text-faint"> · {c.company || c.city}</span>}
            </TargetChip>
          ))}
          <TargetChip active={target === NEW_CONTACT} onClick={() => setTarget(NEW_CONTACT)}>
            <UserPlus className="size-3.5" />
            Новый контакт{foundName ? `: ${foundName}` : ''}
          </TargetChip>
        </div>
        {target === '' && <p className="mt-1.5 text-sm text-muted">Нашлось несколько людей — выберите, к кому это.</p>}
        {isNew && (
          <label className="mt-3 flex flex-col gap-1.5">
            <span className="text-xs font-medium text-muted">
              {foundName ? 'Имя нового контакта' : 'В записи нет имени — как назвать нового человека?'}
            </span>
            <Input
              value={typedName}
              onChange={(e) => setTypedName(e.target.value)}
              placeholder="Имя и фамилия"
              maxLength={200}
              autoFocus={!foundName}
              className="max-w-sm"
            />
          </label>
        )}
      </fieldset>

      <ul className="flex flex-col divide-y divide-line rounded-md border border-line bg-surface">
        {result.actions.map((action) => {
          const { icon: Icon, label } = ACTION_META[action.type];
          const disabled = Boolean(action.error);
          return (
            <li key={action.index}>
              <label className={cn('flex cursor-pointer items-start gap-3 px-3 py-2.5 text-sm', disabled && 'cursor-default opacity-60')}>
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[rgb(var(--accent))]"
                  checked={selected.has(action.index)}
                  disabled={disabled}
                  onChange={() => toggle(action.index)}
                />
                <span className="flex w-20 shrink-0 items-center gap-1.5 text-faint">
                  <Icon className="size-3.5" />
                  {label}
                </span>
                <span className="min-w-0 flex-1 break-words">
                  <ActionBody action={action} />
                  {action.error && <span className="block text-danger">{action.error}</span>}
                </span>
              </label>
            </li>
          );
        })}
      </ul>

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          disabled={!canApply}
          onClick={() => onApply([...selected], isNew ? null : target, isNew ? newName : undefined)}
        >
          Применить {selected.size > 0 ? `(${selected.size})` : ''}
        </Button>
        <Button variant="ghost" onClick={onDiscard} disabled={busy}>
          Отмена
        </Button>
      </div>
    </div>
  );
}

function TargetChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex h-7 items-center gap-1 rounded-full border px-3 text-sm transition-colors',
        active ? 'border-fg bg-fg text-bg [&_.text-faint]:text-bg/70' : 'border-line text-muted hover:bg-hover hover:text-fg',
      )}
    >
      {children}
    </button>
  );
}
