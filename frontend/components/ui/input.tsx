import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const base =
  'w-full rounded-lg bg-transparent text-sm text-fg placeholder:text-faint transition-shadow duration-100 disabled:opacity-50';

/** Обычное поле в рамке (формы, диалоги). */
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        base,
        'h-9 border border-line-strong bg-surface px-3 shadow-xs focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20',
        className,
      )}
      {...props}
    />
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return (
      <textarea
        ref={ref}
        className={cn(
          base,
          'min-h-20 resize-y border border-line-strong bg-surface px-3 py-2 leading-relaxed shadow-xs focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/20',
          className,
        )}
        {...props}
      />
    );
  },
);

/** Поле «как текст»: без рамки, рамка-подсветка только при наведении/фокусе (свойства в карточке). */
export const BareInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function BareInput(
  { className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(base, 'h-8 px-2 hover:bg-hover focus-visible:bg-surface focus-visible:shadow-md', className)}
      {...props}
    />
  );
});
