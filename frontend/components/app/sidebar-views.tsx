'use client';

import { Suspense, useState, type FormEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import useSWR, { useSWRConfig } from 'swr';
import { toast } from 'sonner';
import { ChevronRight, Plus } from 'lucide-react';
import { createGroup, groupsKey, type Group } from '@/lib/api-crm';
import { viewsKey, type ContactView } from '@/lib/api-views';
import { cn, errorText } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Dialog, DialogContent } from '@/components/ui/overlays';

const rowClass =
  'flex h-[28px] min-w-0 flex-1 items-center gap-2 rounded-lg px-2 text-[13px] text-muted transition-colors hover:bg-line/60 hover:text-fg';

/**
 * Секции сайдбара под основной навигацией: сохранённые виды контактов и группы (как Views / Groups в Dex).
 */
export function SidebarViews() {
  return (
    <Suspense fallback={null}>
      <SidebarViewsInner />
    </Suspense>
  );
}

function SidebarViewsInner() {
  const params = useSearchParams();
  const activeView = params.get('view');
  const activeGroup = params.get('group');
  const router = useRouter();
  const { data: views = [] } = useSWR<ContactView[]>(viewsKey());
  const { data: groups = [] } = useSWR<Group[]>(groupsKey());
  const [isGroupDialogOpen, setIsGroupDialogOpen] = useState(false);

  return (
    <div className="mt-4 flex flex-col gap-3">
      <Section
        title="Виды"
        addLabel="Новый вид"
        onAdd={() => router.push('/contacts?newview=1')}
        isEmpty={views.length === 0}
        emptyText="Сохраните фильтры как вид"
      >
        {views.map((v) => (
          <Link
            key={v.id}
            href={`/contacts?view=${v.id}`}
            className={cn(rowClass, 'flex-none', activeView === v.id && 'bg-line font-medium text-fg')}
          >
            <span className="w-4 shrink-0 text-center">{v.emoji || '•'}</span>
            <span className="truncate">{v.name}</span>
          </Link>
        ))}
      </Section>

      <Section
        title="Группы"
        addLabel="Новая группа"
        onAdd={() => setIsGroupDialogOpen(true)}
        isEmpty={groups.length === 0}
        emptyText="Групп пока нет"
      >
        {groups.map((g) => (
          <Link
            key={g.id}
            href={`/contacts?group=${g.id}`}
            className={cn(rowClass, 'flex-none', activeGroup === g.id && 'bg-line font-medium text-fg')}
          >
            <span className="w-4 shrink-0 text-center">{g.emoji || '•'}</span>
            <span className="flex-1 truncate">{g.name}</span>
            {g.member_count > 0 && <span className="tabular text-xs text-faint">{g.member_count}</span>}
          </Link>
        ))}
      </Section>

      <NewGroupDialog open={isGroupDialogOpen} onOpenChange={setIsGroupDialogOpen} />
    </div>
  );
}

function Section({
  title,
  addLabel,
  onAdd,
  isEmpty,
  emptyText,
  children,
}: {
  title: string;
  addLabel: string;
  onAdd: () => void;
  isEmpty: boolean;
  emptyText: string;
  children: ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(true);
  return (
    <section aria-label={title} className="px-2">
      <div className="group/section flex items-center">
        <button
          type="button"
          onClick={() => setIsOpen((o) => !o)}
          aria-expanded={isOpen}
          className="flex h-6 flex-1 items-center gap-1 rounded-lg px-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint hover:text-muted"
        >
          <ChevronRight className={cn('size-3 transition-transform', isOpen && 'rotate-90')} aria-hidden />
          {title}
        </button>
        <button
          type="button"
          onClick={onAdd}
          aria-label={addLabel}
          title={addLabel}
          className="flex size-6 items-center justify-center rounded-lg text-faint hover:bg-line/60 hover:text-fg"
        >
          <Plus className="size-3.5" />
        </button>
      </div>
      {isOpen && (
        <div className="mt-0.5 flex flex-col gap-px">
          {isEmpty ? <div className="px-2 py-1 text-xs text-faint">{emptyText}</div> : children}
        </div>
      )}
    </section>
  );
}

function NewGroupDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const { mutate } = useSWRConfig();
  const [name, setName] = useState('');
  const [emoji, setEmoji] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setIsSaving(true);
    try {
      const group = await createGroup({ name: name.trim(), emoji: emoji.trim() });
      await mutate(groupsKey());
      setName('');
      setEmoji('');
      onOpenChange(false);
      router.push(`/contacts?group=${group.id}`);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Новая группа" description="Группа собирает людей: семья, коллеги, клуб.">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex gap-2">
            <Input
              aria-label="Эмодзи"
              placeholder="🙂"
              value={emoji}
              maxLength={4}
              onChange={(e) => setEmoji(e.target.value)}
              className="w-14 text-center"
            />
            <Input autoFocus aria-label="Название" placeholder="Название группы" value={name} onChange={(e) => setName(e.target.value)} />
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
