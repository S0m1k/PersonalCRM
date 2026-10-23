'use client';

/**
 * Редакторы значений свойств в духе Notion: в покое — текст, по клику — поле ввода.
 * Сохранение по Enter / уходу фокуса, отмена по Esc.
 */

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Check, ChevronDown, ExternalLink } from 'lucide-react';
import type { FieldDef, FieldValue } from '@/lib/api';
import { cn, formatDate, safeUrl } from '@/lib/utils';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/overlays';
import { Tag } from '@/components/ui/tag';

const shell =
  'flex min-h-8 w-full items-center rounded px-2 text-left text-sm transition-colors hover:bg-hover focus-visible:bg-hover';
const fieldClass = 'w-full rounded bg-surface px-2 text-sm text-fg shadow-pop outline-none';

const Empty = ({ label = 'Пусто' }: { label?: string }) => <span className="text-faint">{label}</span>;

type EditableTextProps = {
  value: string;
  onCommit: (value: string) => void;
  placeholder?: string;
  type?: 'text' | 'date' | 'number' | 'url' | 'email' | 'tel';
  isMultiline?: boolean;
  display?: ReactNode;
  className?: string;
  ariaLabel?: string;
};

export function EditableText({
  value,
  onCommit,
  placeholder,
  type = 'text',
  isMultiline = false,
  display,
  className,
  ariaLabel,
}: EditableTextProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const ref = useRef<HTMLInputElement & HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!isEditing) setDraft(value);
  }, [value, isEditing]);

  useEffect(() => {
    if (isEditing) ref.current?.focus();
  }, [isEditing]);

  function commit() {
    setIsEditing(false);
    if (draft.trim() !== value.trim()) onCommit(draft.trim());
  }

  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      setDraft(value);
      setIsEditing(false);
    } else if (e.key === 'Enter' && (!isMultiline || e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      commit();
    }
  }

  if (isEditing) {
    const common = {
      ref,
      value: draft,
      'aria-label': ariaLabel,
      onChange: (e: { target: { value: string } }) => setDraft(e.target.value),
      onBlur: commit,
      onKeyDown: handleKey,
      placeholder,
    };
    return isMultiline ? (
      <textarea {...common} rows={Math.max(3, draft.split('\n').length)} className={cn(fieldClass, 'resize-y py-1.5 leading-relaxed', className)} />
    ) : (
      <input {...common} type={type} className={cn(fieldClass, 'h-8', className)} />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setIsEditing(true)}
      aria-label={ariaLabel}
      className={cn(shell, isMultiline && 'items-start whitespace-pre-wrap py-1.5 leading-relaxed', className)}
    >
      {value ? display ?? value : <Empty label={placeholder} />}
    </button>
  );
}

type SelectValueProps = {
  value: string;
  options: string[];
  onCommit: (value: string) => void;
  placeholder?: string;
  renderOption?: (option: string) => ReactNode;
};

export function SelectValue({ value, options, onCommit, placeholder, renderOption }: SelectValueProps) {
  const [open, setOpen] = useState(false);
  const render = renderOption ?? ((o: string) => <Tag>{o}</Tag>);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger className={cn(shell, 'group justify-between')}>
        {value ? render(value) : <Empty label={placeholder} />}
        <ChevronDown className="size-3.5 text-faint opacity-0 group-hover:opacity-100" />
      </PopoverTrigger>
      <PopoverContent className="w-56">
        {options.map((option) => (
          <button
            key={option}
            type="button"
            onClick={() => {
              setOpen(false);
              if (option !== value) onCommit(option);
            }}
            className="flex h-8 w-full items-center justify-between gap-2 rounded px-2 text-left text-sm hover:bg-hover"
          >
            {render(option)}
            {option === value && <Check className="size-4 text-muted" />}
          </button>
        ))}
        {value && (
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              onCommit('');
            }}
            className="mt-1 flex h-8 w-full items-center rounded border-t border-line px-2 text-left text-sm text-muted hover:bg-hover"
          >
            Очистить
          </button>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** Значение поля шаблона по его типу. */
export function FieldValueEditor({
  def,
  value,
  onCommit,
}: {
  def: FieldDef;
  value: FieldValue | undefined;
  onCommit: (value: FieldValue | '') => void;
}) {
  const text = value === undefined || value === null ? '' : String(value);

  switch (def.type) {
    case 'select':
      return <SelectValue value={text} options={def.options} onCommit={onCommit} />;
    case 'bool':
      return (
        <button
          type="button"
          role="checkbox"
          aria-checked={value === true}
          aria-label={def.label}
          onClick={() => onCommit(!(value === true))}
          className={cn(shell, 'w-auto')}
        >
          <span
            className={cn(
              'flex size-4 items-center justify-center rounded-[3px] border-[1.5px] transition-colors',
              value === true ? 'border-accent bg-accent text-accent-fg' : 'border-faint',
            )}
          >
            {value === true && <Check className="size-3" strokeWidth={3} />}
          </span>
        </button>
      );
    case 'date':
      return <EditableText type="date" value={text} onCommit={onCommit} display={formatDate(text)} ariaLabel={def.label} />;
    case 'number':
      return <EditableText type="number" value={text} onCommit={onCommit} display={<span className="tabular">{Number(text).toLocaleString('ru-RU')}</span>} ariaLabel={def.label} />;
    case 'url': {
      const href = safeUrl(text);
      return (
        <EditableText
          value={text}
          onCommit={onCommit}
          ariaLabel={def.label}
          display={
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="truncate underline decoration-line underline-offset-4">{text.replace(/^https?:\/\//, '')}</span>
              {href && (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="shrink-0 text-faint hover:text-fg"
                  aria-label="Открыть ссылку"
                >
                  <ExternalLink className="size-3.5" />
                </a>
              )}
            </span>
          }
        />
      );
    }
    case 'longtext':
      return <EditableText isMultiline value={text} onCommit={onCommit} ariaLabel={def.label} />;
    default:
      return <EditableText value={text} onCommit={onCommit} ariaLabel={def.label} />;
  }
}

/** Строка свойства: подпись слева, значение справа. */
export function PropertyRow({ icon, label, children }: { icon: ReactNode; label: ReactNode; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_1fr] items-start gap-1 sm:grid-cols-[minmax(120px,170px)_1fr]">
      <div className="flex h-8 items-center gap-2 px-1 text-sm text-muted [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-faint">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className="min-w-0">{children}</div>
    </div>
  );
}
