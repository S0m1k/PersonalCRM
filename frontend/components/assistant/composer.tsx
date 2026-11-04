'use client';

import { useRef, type FormEvent, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import { cn } from '@/lib/utils';

export const MESSAGE_MAX = 4000;

type Props = {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
  onSubmit: () => void;
  className?: string;
};

/** Поле ввода: Enter — отправить, Shift+Enter — новая строка; кнопка внутри рамки справа внизу. */
export function Composer({ value, disabled, onChange, onSubmit, className }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const canSend = value.trim().length > 0 && !disabled;

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter во время ввода через IME (isComposing) не отправляем
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onSubmit();
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (canSend) onSubmit();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className={cn(
        'relative rounded-2xl border border-line-strong bg-surface shadow-xs transition-shadow focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent/20',
        className,
      )}
    >
      <textarea
        ref={ref}
        value={value}
        rows={2}
        maxLength={MESSAGE_MAX}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Спросите про контакты или запишите встречу…"
        aria-label="Сообщение помощнику"
        className="block max-h-48 min-h-[4.5rem] w-full resize-none bg-transparent px-4 pb-12 pt-3.5 text-[15px] leading-relaxed text-fg placeholder:text-faint focus:outline-none"
      />
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Отправить"
        className="absolute bottom-2.5 right-2.5 flex size-8 items-center justify-center rounded-full bg-accent text-accent-fg transition-colors hover:bg-accent-hover disabled:opacity-40"
      >
        <ArrowUp className="size-4" />
      </button>
    </form>
  );
}
