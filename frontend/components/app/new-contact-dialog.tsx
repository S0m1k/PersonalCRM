'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { createContact, type Template } from '@/lib/api';
import { cn, errorText } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';

type Props = {
  open: boolean;
  initialName: string;
  onOpenChange: (open: boolean) => void;
};

/** Имя → шаблон → «Создать». Остальное заполняется прямо на странице контакта. */
export function NewContactDialog({ open, initialName, onOpenChange }: Props) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const { data: templates = [] } = useSWR<Template[]>(open ? '/api/templates' : null);
  const [name, setName] = useState('');
  const [templateId, setTemplateId] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setName(initialName);
      setTemplateId(null);
    }
  }, [open, initialName]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const [first, ...rest] = name.trim().split(/\s+/);
    if (!first) return;
    setIsSaving(true);
    try {
      const contact = await createContact({ first_name: first, last_name: rest.join(' '), template_id: templateId });
      void mutate((key) => typeof key === 'string' && (key.startsWith('/api/contacts') || key.startsWith('/api/home')));
      onOpenChange(false);
      router.push(`/contacts/${contact.id}`);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Новый контакт" description="Остальное можно дописать на странице контакта или надиктовать позже.">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Input autoFocus placeholder="Имя и фамилия" value={name} onChange={(e) => setName(e.target.value)} />
          <div>
            <div className="mb-1.5 text-xs font-medium text-muted">Шаблон карточки</div>
            <div className="flex flex-wrap gap-1.5">
              <TemplateChip label="Без шаблона" icon="📄" isActive={templateId === null} onClick={() => setTemplateId(null)} />
              {templates.map((t) => (
                <TemplateChip
                  key={t.id}
                  label={t.name}
                  icon={t.icon}
                  isActive={templateId === t.id}
                  onClick={() => setTemplateId(t.id)}
                />
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Отмена
            </Button>
            <Button type="submit" variant="primary" disabled={!name.trim() || isSaving}>
              {isSaving ? 'Создаю…' : 'Создать'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TemplateChip({ label, icon, isActive, onClick }: { label: string; icon: string; isActive: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[13px] transition-colors',
        isActive ? 'border-accent bg-accent/10 text-fg' : 'border-line text-muted hover:bg-hover hover:text-fg',
      )}
    >
      <span aria-hidden>{icon}</span>
      {label}
    </button>
  );
}
