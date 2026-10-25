import type { FormEvent, ReactNode } from 'react';

/** Каркас страниц входа и регистрации: логотип, подзаголовок, форма в карточке, ссылка под ней. */
export function AuthCard({
  subtitle,
  onSubmit,
  footer,
  children,
}: {
  subtitle: string;
  onSubmit: (e: FormEvent) => void;
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-sidebar px-4">
      <div className="w-full max-w-[340px] animate-fade-up">
        <div className="mb-8 text-center">
          <span className="mx-auto mb-4 flex size-11 items-center justify-center rounded-lg bg-fg font-serif text-2xl font-bold italic text-bg">
            P
          </span>
          <h1 className="text-xl font-semibold tracking-tight">PersonalCRM</h1>
          <p className="mt-1 text-sm text-muted">{subtitle}</p>
        </div>

        <form onSubmit={onSubmit} className="flex flex-col gap-3 rounded-lg bg-surface p-5 shadow-pop">
          {children}
        </form>

        <p className="mt-4 text-center text-sm text-muted">{footer}</p>
      </div>
    </main>
  );
}

export function AuthField({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </label>
  );
}

export function AuthError({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p role="alert" className="text-sm text-danger">
      {message}
    </p>
  );
}
